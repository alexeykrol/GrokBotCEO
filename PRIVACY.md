# BotCEO Privacy Policy

Version A-2.2 · Effective date: 23 November 2026 · Published at https://github.com/alexeykrol/GrokBotCEO (file `PRIVACY.md`)

Applies to these versions only: 0.1.0-rc7 and 0.2.0 (published as GrokBotCEO), and the closed-test
releases 0.3.0 and later 0.3.x, which all handle personal information in the same way. A release
that handles it differently is covered only by a new version of this policy.

## 1. Who we are

BotCEO is published by Alexey Krol, an individual (sole proprietor) based in California, USA
("we", "us"). Postal address: see section 1 of the Terms of Use.
Privacy contact: support@alexeykrol.com.

## 2. What the software is

BotCEO is a set of bot instructions and a course that you load into your own Grok Bot workspace.
It runs inside your workspace; we do not run it for you. Starting with release
0.3.0, it is published with licenses: the bots and the software under the BotCEO
License 1.0, the course materials under the BotCEO Course License, together with the
Terms of Use (file `TERMS.md` in the same repository). Earlier releases were published under the name GrokBotCEO and without a
license file.
The software contains no advertising pixels and no web analytics tools. Starting with release
0.3.0, which is a closed test, remarks you write about the course are sent to the
author (section 4). Earlier releases send us nothing.

## 2a. Our approach, in short

There are two kinds of information, and we treat them differently.

- **Automatically collected technical information.** The software sends us no telemetry. The server
  that receives course remarks keeps standard access logs, including IP addresses, briefly, for security and
  operation (section 4).
- **Anything that comes from you as a person** — an email, a question, feedback, a wish. We receive
  it only when you choose to send it, keep it as long as we need it or the law requires, and use it
  only for the purpose you sent it for: in these versions, your remarks about the course (section 4)
  and email to us (section 5).

Your conversations with your bots, your bot settings, your quiz answers and your course progress stay
in your workspace.

## 3. What this policy covers

The versions named above, the server that receives course remarks, the GitHub repository where the
releases are published, and email you send us about BotCEO.

It does not cover websites. A web page where you read this policy or learn about BotCEO belongs
to a website with its own privacy policy, and that policy governs your visit to the page — including
any cookies or analytics the website uses. For our own website, see the privacy policy published
on that website.

## 4. Course remarks

**Releases before 0.3.0.** The package configures no receiving address and the
installer adds none, so the course sends us nothing.

**Releases 0.3.x (closed test).** The closed test exists to improve the course,
so remarks about the course go to its author:

- **What is sent.** Only the text that you write to the course teacher (the Mentor bot) as a remark
  about the course, up to 1,000 characters, together with technical details of the remark: the
  lesson or course it refers to, its kind (unclear, wrong or other), the course and release version,
  the time, a random number for the remark, a link to an earlier remark of yours if this one
  continues it, the chat platform's number of the message when the platform provides one, and a
  random installation ID created when you install. The ID lets us
  see that several remarks come from the same installation. It is not your name, account or email,
  and we do not link it to your invitation or to anything else that says who you are.
- **What is never sent.** The rest of your conversation, your quiz answers, your course progress,
  your name, your bot settings or your files. Please do not put personal information about yourself
  or others into a remark.
- **How you are told and how you stop it.** The installation message tells you about remarks before
  you confirm the installation, and the course teacher tells you again when the course starts, before
  any remark is sent. Say "не отправляй" ("do not send") to the course teacher at any time and
  sending stops at once; say "снова отправляй" ("send again") to resume. Remarks you write while
  sending is stopped stay in your workspace and are never sent. If a remark cannot be delivered, it
  waits in your workspace and is sent later; a remark that was still waiting when you stopped is
  sent only after you resume.
- **Where it goes.** To our course-remarks server, hosted by Hostinger International Limited on our
  behalf in the United States. Its address is in the file `course/feedback.json` of the package. We use remarks only to fix and improve the course and BotCEO.
- **How long we keep it.** Remarks are deleted from the server 180 days after we receive them, and
  from its backups within a further 14 days. We may keep what we learned from a remark — for
  example a corrected lesson — but not the remark itself.
- **Server logs.** Like any web service, the server keeps a standard access log — IP address,
  request path, status and timing, never the content of a remark — for security and operation. The
  log is kept briefly: it is limited in size, and old entries are overwritten by new ones. IP addresses are not stored with remarks, and we do not use them to
  identify people.

The installer also keeps a record that you accepted the Terms of Use, and the course keeps a record
of your choice about remarks. Both records stay in your workspace, and we do not receive them.

## 5. Information that we or others do process

- **GitHub.** Downloads, issues and other activity on the repository are processed by GitHub under the
  GitHub Privacy Statement. Issues are public: please do not post personal information in them. We read
  issues to fix problems and improve the software.
- **Email to us.** If you write to our privacy contact (section 1) about BotCEO, we receive your email
  address and your message. We use them to answer you, to fix problems and, when your message contains a
  suggestion or a report, to improve BotCEO. We keep them for 24 months after your last message. We keep the record of a privacy request for
  24 months after we answer it.
- **Grok Bot (your platform, not us).** Your bots and the course run inside Grok Bot, which you use under
  your own account terms. Under the published architecture, app requests go to Cursor's servers, work
  runs on Cursor-operated hosted computers, prompts go to model providers, and tool calls reach
  services you connect ([Grok Bot security](https://docs.x.ai/grok-bot/security)). Grok Bot is
  provided by Anysphere, Inc. (Cursor) under the
  [X-Subscription Terms](https://x.ai/legal/x-subscription-terms-of-service) and the
  [Cursor Privacy Policy](https://cursor.com/privacy); SpaceX Super Intelligence LLC's
  [Privacy Policy](https://x.ai/legal/privacy-policy) covers its own services. Which terms apply to
  you depends on your account. We are not part of this processing and do not receive it.

## 6. Sale and sharing

Information we receive through BotCEO (course remarks, repository activity and email to us) is not
sold, is not shared for advertising, and is not disclosed to anyone except the service providers that
work on our behalf — the host of the server that receives course remarks (Hostinger International Limited) and
our email providers (Titan, titan.email, which hosts the support mailbox, and Amazon Web Services,
which delivers email we send) — which process it only to
provide that service, and except where the law requires disclosure.

## 7. Do Not Track

The BotCEO software contains no advertising or web tracking technology, so a browser "Do Not
Track" signal changes nothing in how the software works. The platform that runs your workspace and the
websites you visit follow their own policies (sections 3 and 5).

## 8. Children

BotCEO is intended for adults (18+) and is not directed to children. We do not knowingly collect
personal information from children. If we learn that we have, we delete it.

## 9. Your choices and requests

Wherever you live, you can ask us to access, delete, export or correct personal information we hold
about you, and you can withdraw any consent you gave. Write to our privacy contact (section 1) with the subject line "BotCEO
privacy request". We answer within 30
days, or sooner where applicable law requires. We may ask you to confirm that the information is
yours before we act.

Course remarks are stored under your installation ID, not your name. To get a copy of your remarks or
have them deleted, send us that ID; the course teacher shows it when you ask "покажи мой ID"
("show my ID"). Stopping the sending (section 4) needs no request to us.

If you are in the European Economic Area, the United Kingdom or Switzerland: we process your email to
us and keep server logs on the basis of our legitimate interests (answering you, improving BotCEO,
keeping our server secure), and we process your course remarks on the basis of your consent, which
you give when you confirm the installation and can withdraw at any time by stopping the sending
(section 4). You may object to processing based on legitimate interests, and you may complain to your
data protection authority. We are based in the United States and process the information there.

## 10. Changes

Each version of this policy has a version number and an effective date. Past versions are kept in the
history of this file in the repository named at the top. Before we start any new collection of information, we update this policy and give
notice in the release notes and the README of the release before the change takes effect. Sending
anything beyond the course remarks of section 4 — for example quiz answers or telemetry — needs a
new version of this policy first.

## 11. Language

This policy is written in English. Translations are provided for convenience only; the English
version controls.
