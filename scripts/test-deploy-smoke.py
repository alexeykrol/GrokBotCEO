#!/usr/bin/env python3
"""Regression tests for services/feedback-receiver/deploy/smoke.sh (Codex rc2 review P2-1).

The smoke must POSITIVELY confirm its target before any HTTP request, and stop before any write
when Docker fails, times out, shows an unexpected container/project/volume/port/route, or when
/healthz is not 200/ok. Everything runs against fake `docker`, `curl` and `timeout` executables
on PATH: no real Docker, no network. Each refusal case must log zero HTTP mutations (POST).
"""
import json
import os
import shutil
import stat
import subprocess
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
SMOKE = os.environ.get("SMOKE_SH_UNDER_TEST") or os.path.join(ROOT, "services", "feedback-receiver", "deploy", "smoke.sh")

FAKE_TIMEOUT = r"""#!/usr/bin/env python3
import os, sys
args = sys.argv[1:]
while args and args[0].startswith("--"):
    args.pop(0)
args.pop(0)  # duration
os.execvp(args[0], args)
"""

FAKE_DOCKER = r"""#!/usr/bin/env python3
import json, os, sys
mode = os.environ.get("FAKE_DOCKER", "ok")
GOOD_RULE = ("Host(`course-feedback.example.test`) && "
             "(Path(`/healthz`) || Path(`/v1/register`) || Path(`/v1/course-event`))")
log = os.environ["FAKE_LOG"]
args = sys.argv[1:]
with open(log, "a") as f:
    f.write("docker " + " ".join(args[:1]) + "\n")
if mode == "rc42":
    sys.exit(42)
if mode == "rc124":
    sys.exit(124)
name = os.environ.get("FAKE_NAME", "fr-course-smoke-receiver")
project = os.environ.get("FAKE_PROJECT", "fr-course-smoke")
volume = os.environ.get("FAKE_VOLUME", "fr-course-smoke-data")
if args[0] == "ps":
    names = [] if mode == "notrunning" else [name]
    if mode == "both":
        names.append("fr-course-receiver" if name != "fr-course-receiver" else "fr-course-smoke-receiver")
    names.append("unrelated-neighbour")
    print("\n".join(names))
    sys.exit(0)
if args[0] == "inspect":
    if mode == "inspect_bad":
        print("not json"); sys.exit(0)
    c = {"Name": "/" + name,
         "State": {"Running": True, "Health": {"Status": "starting" if mode == "unhealthy" else "healthy"}},
         "Config": {"Labels": {"com.docker.compose.project": "other" if mode == "wrongproject" else project,
                               "traefik.enable": os.environ.get("FAKE_TRAEFIK", "false"),
                               "traefik.http.routers.fr-course.entrypoints": os.environ.get("FAKE_EP", "websecure"),
                               "traefik.http.routers.fr-course.tls": "true",
                               "traefik.http.routers.fr-course.rule": os.environ.get("FAKE_RULE", GOOD_RULE)}},
         "Mounts": [{"Type": "volume", "Destination": "/data",
                     "Name": "fr-course-data" if mode == "wrongvolume" else volume}],
         "HostConfig": {"PortBindings": {"8080/tcp": [{"HostIp": "0.0.0.0" if mode == "wrongport" else "127.0.0.1",
                                                      "HostPort": "18080"}]}}}
    print(json.dumps([c]))
    sys.exit(0)
if args[0] == "exec":
    print(json.dumps({"course": {"counts": {"events": 1}}}))
    sys.exit(0)
sys.exit(1)
"""

FAKE_CURL = r"""#!/usr/bin/env python3
import json, os, sys
args = sys.argv[1:]
out, method, url, data, auth = None, "GET", args[-1], None, False
i = 0
while i < len(args):
    a = args[i]
    if a == "-o": out = args[i + 1]; i += 2; continue
    if a == "-X": method = args[i + 1]; i += 2; continue
    if a == "--data-binary": data = args[i + 1]; i += 2; continue
    if a == "-H":
        if args[i + 1].endswith("auth.hdr"): auth = True
        i += 2; continue
    i += 1
path = "/" + url.split("://", 1)[1].split("/", 1)[1]
state = os.environ["FAKE_STATE"]
with open(os.environ["FAKE_LOG"], "a") as f:
    f.write("http %s %s\n" % (method, path))
code, body = 404, {}
if path == "/healthz":
    code = int(os.environ.get("FAKE_HEALTH", "200")); body = {"status": "ok"} if code == 200 else {}
elif path == "/v1/register" and method == "POST":
    code, body = 201, {"install_id": "i-1", "send_token": "t-secret"}
elif path == "/v1/course-event" and method == "POST":
    if not auth:
        code = 401
    elif data and data.endswith("big.json"):
        code = 413
    else:
        ev = json.load(open(data[1:]))["events"][0]["id"]
        seen = os.path.exists(state)
        open(state, "w").write(ev)
        code, body = 200, ({"accepted": [], "duplicate": [ev]} if seen else {"accepted": [ev], "duplicate": []})
with open(out, "w") as f:
    json.dump(body, f)
sys.stdout.write(str(code))
"""


class SmokePreflight(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="smoke-test-")
        self.bin = os.path.join(self.tmp, "bin")
        os.mkdir(self.bin)
        for name, src in (("timeout", FAKE_TIMEOUT), ("docker", FAKE_DOCKER), ("curl", FAKE_CURL)):
            p = os.path.join(self.bin, name)
            with open(p, "w") as f:
                f.write(src)
            os.chmod(p, stat.S_IRWXU)
        self.log = os.path.join(self.tmp, "calls.log")

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def run_smoke(self, **env):
        e = {"PATH": self.bin + os.pathsep + os.environ["PATH"], "HOME": self.tmp,
             "FAKE_LOG": self.log, "FAKE_STATE": os.path.join(self.tmp, "state")}
        e.update(env)
        r = subprocess.run(["bash", SMOKE], env=e, capture_output=True, text=True, timeout=60)
        calls = []
        if os.path.exists(self.log):
            with open(self.log) as f:
                calls = f.read().splitlines()
        return r, calls

    def assert_refused(self, r, calls, rc=None):
        self.assertNotEqual(r.returncode, 0, r.stdout + r.stderr)
        if rc is not None:
            self.assertEqual(r.returncode, rc, r.stderr)
        self.assertEqual([c for c in calls if c.startswith("http POST")], [], calls)
        self.assertNotIn("t-secret", r.stdout + r.stderr)

    def test_positive_staging(self):
        r, calls = self.run_smoke()
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("FAILS=0", r.stdout)
        self.assertIn("target confirmed", r.stderr + r.stdout)
        self.assertEqual(calls[:2], ["docker ps", "docker inspect"])
        self.assertNotIn("t-secret", r.stdout + r.stderr)

    def test_positive_public_pilot(self):
        r, calls = self.run_smoke(SMOKE_BASE_URL="https://course-feedback.example.test", SMOKE_ALLOW_PUBLIC="1",
                                  SMOKE_CONTAINER="fr-course-receiver", FAKE_NAME="fr-course-receiver",
                                  FAKE_PROJECT="fr-course", FAKE_VOLUME="fr-course-pilot-data", FAKE_TRAEFIK="true")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)

    def test_docker_error_stops_without_http(self):
        r, calls = self.run_smoke(FAKE_DOCKER="rc42")
        self.assert_refused(r, calls, rc=3)
        self.assertEqual([c for c in calls if c.startswith("http")], [])

    def test_docker_timeout_stops_with_124_without_http(self):
        r, calls = self.run_smoke(FAKE_DOCKER="rc124")
        self.assert_refused(r, calls, rc=124)
        self.assertEqual(len([c for c in calls if c.startswith("docker")]), 1)  # no retry
        self.assertEqual([c for c in calls if c.startswith("http")], [])

    def test_unconfirmed_targets_stop_without_http(self):
        for mode in ("notrunning", "both", "inspect_bad", "unhealthy", "wrongproject", "wrongvolume", "wrongport"):
            with self.subTest(mode=mode):
                if os.path.exists(self.log):
                    os.remove(self.log)
                r, calls = self.run_smoke(FAKE_DOCKER=mode)
                self.assert_refused(r, calls, rc=2)
                self.assertEqual([c for c in calls if c.startswith("http")], [])

    def test_public_without_enabled_route_or_wrong_host_refused(self):
        base = dict(SMOKE_ALLOW_PUBLIC="1", SMOKE_CONTAINER="fr-course-receiver", FAKE_NAME="fr-course-receiver",
                    FAKE_PROJECT="fr-course", FAKE_VOLUME="fr-course-pilot-data")
        for extra in ({"SMOKE_BASE_URL": "https://course-feedback.example.test", "FAKE_TRAEFIK": "false"},
                      {"SMOKE_BASE_URL": "https://other.example.test", "FAKE_TRAEFIK": "true"}):
            with self.subTest(extra=extra):
                if os.path.exists(self.log):
                    os.remove(self.log)
                r, calls = self.run_smoke(**base, **extra)
                self.assert_refused(r, calls, rc=2)

    def test_public_rule_must_be_exact(self):
        base = dict(SMOKE_ALLOW_PUBLIC="1", SMOKE_CONTAINER="fr-course-receiver", FAKE_NAME="fr-course-receiver",
                    FAKE_PROJECT="fr-course", FAKE_VOLUME="fr-course-pilot-data", FAKE_TRAEFIK="true",
                    SMOKE_BASE_URL="https://course-feedback.example.test")
        for extra in ({"FAKE_RULE": "!Host(`course-feedback.example.test`) && PathPrefix(`/`)"},
                      {"FAKE_RULE": "Host(`course-feedback.example.test`) || PathPrefix(`/`)"},
                      {"FAKE_RULE": "Host(`course-feedback.example.test`) && (Path(`/healthz`) || Path(`/v1/register`))"},
                      {"FAKE_RULE": "Host(`x.example.test`) || Host(`course-feedback.example.test`) && "
                                    "(Path(`/healthz`) || Path(`/v1/register`) || Path(`/v1/course-event`))"},
                      {"FAKE_EP": "web"}):
            with self.subTest(extra=extra):
                if os.path.exists(self.log):
                    os.remove(self.log)
                r, calls = self.run_smoke(**base, **extra)
                self.assert_refused(r, calls, rc=2)
                self.assertEqual([c for c in calls if c.startswith("http")], [])

    def test_non_canonical_urls_refused_before_docker(self):
        for url in ("http://127.0.0.1:18080" + "@" + "other.example.test:18080", "http://localhost:18080",
                    "http://127.0.0.1:18081", "http://127.0.0.1", "http://127.0.0.1:18080/",
                    "http://127.0.0.1:18080/x", "http://user@127.0.0.1:18080", "http://[::1]:18080",
                    "https://course-feedback.example.test:8443", "https://u:p" + "@" + "course-feedback.example.test",
                    "https://course-feedback.example.test/", "https://course-feedback.example.test/x",
                    "https://course-feedback.example.test?x=1", "https://course-feedback.example.test#f",
                    "https://Course-Feedback.example.test", "https://course-feedback", "ftp://127.0.0.1:18080",
                    "http://course-feedback.example.test", " http://127.0.0.1:18080"):
            with self.subTest(url=url):
                if os.path.exists(self.log):
                    os.remove(self.log)
                r, calls = self.run_smoke(SMOKE_BASE_URL=url, SMOKE_ALLOW_PUBLIC="1",
                                          SMOKE_CONTAINER="fr-course-receiver", FAKE_NAME="fr-course-receiver",
                                          FAKE_PROJECT="fr-course", FAKE_VOLUME="fr-course-pilot-data",
                                          FAKE_TRAEFIK="true")
                self.assert_refused(r, calls, rc=2)
                self.assertEqual(calls, [])

    def test_real_students_volume_and_unknown_container_refused_before_docker(self):
        for env in ({"SMOKE_CONTAINER": "fr-course-receiver", "SMOKE_VOLUME": "fr-course-data"},
                    {"SMOKE_CONTAINER": "aichattg-bot"}):
            with self.subTest(env=env):
                if os.path.exists(self.log):
                    os.remove(self.log)
                r, calls = self.run_smoke(**env)
                self.assert_refused(r, calls, rc=2)
                self.assertEqual(calls, [])

    def test_bad_health_stops_before_any_post(self):
        r, calls = self.run_smoke(FAKE_HEALTH="503")
        self.assert_refused(r, calls, rc=1)
        self.assertEqual([c for c in calls if c.startswith("http")], ["http GET /healthz"])


if __name__ == "__main__":
    unittest.main(verbosity=1 if "-v" not in sys.argv else 2)
