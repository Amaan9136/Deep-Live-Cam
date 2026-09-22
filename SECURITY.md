# Security Policy

## Supported Versions

faceswap-live is developed on a single rolling `main` branch. Only the
latest commit on `main` receives security fixes.

| Version         | Supported          |
| --------------- | ------------------ |
| `main` (latest) | :white_check_mark: |
| Older snapshots | :x:                 |

## Reporting a Vulnerability

Please **do not open a public issue** for security vulnerabilities.

Instead, report it privately using one of the following:

1. **GitHub Security Advisories** (preferred): open a
   [private security advisory](https://github.com/Amaan9136/faceswap-live/security/advisories/new)
   for this repository.
2. Contact the maintainer, [@Amaan9136](https://github.com/Amaan9136),
   directly via GitHub.

When reporting, please include:

- A description of the vulnerability and its potential impact
- Steps to reproduce it (a minimal example helps a lot)
- Any relevant logs, stack traces, or request/response payloads
- Your assessment of severity, if you have one

You should expect an initial response within a few days. If the issue
is confirmed, a fix will be prioritized and a coordinated disclosure
timeline will be worked out with you before any public details are
shared.

## Scope Notes

This project runs entirely **locally** by design — there is no cloud
service, hosted instance, or multi-tenant deployment maintained by the
project. Most relevant security concerns are therefore local-machine
issues, such as:

- Path traversal or unsafe file handling in upload/output endpoints
  (`/api/swap`, `/api/outputs/*`)
- Resource exhaustion via the realtime streaming endpoints
  (`/api/realtime/*`)
- Unsafe deserialization or injection in request handling (`web/app.py`)
- Dependency vulnerabilities in `requirements.txt`

If you're deploying this application in a way it wasn't designed for
(e.g. exposed to an untrusted network rather than `127.0.0.1`), please
say so in your report — the threat model changes significantly and it
helps us scope the fix correctly.

## Responsible Use

This software performs face swapping, including real-time webcam face
swapping. Misuse to impersonate real individuals without consent, to
harass, defame, or deceive, or to create non-consensual intimate
imagery, is strictly outside the intended and supported use of this
project. See the upstream
[Deep-Live-Cam](https://github.com/hacksider/Deep-Live-Cam) project for
its usage guidelines, which this project also follows.