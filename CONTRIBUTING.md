# Contributing to faceswap-live

First off, thanks for taking the time to contribute. This project is a solo-maintained
fork that adds a local web/streaming layer on top of
[Deep-Live-Cam](https://github.com/hacksider/Deep-Live-Cam), and community contributions
are what will keep it moving. Whether it's a bug report, a doc fix, or a new feature,
it's genuinely welcome.

## Before you start

- Read the [Code of Conduct](CODE_OF_CONDUCT.md). Be kind, this is a small project run
  by volunteers.
- Check [open issues](https://github.com/Amaan9136/faceswap-live/issues) and
  [discussions](https://github.com/Amaan9136/faceswap-live/discussions) first, someone
  may have already reported or started on your idea.
- For anything in the core face-swap engine itself (as opposed to the web/streaming
  layer), consider whether it belongs upstream in
  [Deep-Live-Cam](https://github.com/hacksider/Deep-Live-Cam) instead.

## Ways to contribute

- **Report bugs** using the [bug report template](.github/ISSUE_TEMPLATE/bug_report.yml).
- **Suggest features** using the
  [feature request template](.github/ISSUE_TEMPLATE/feature_request.yml).
- **Improve docs** — README clarity, setup instructions, code comments, architecture
  diagrams.
- **Submit code** — bug fixes, new endpoints, UI polish, performance work, new enhancer
  backends, etc.
- **Triage issues** — reproducing bugs, adding detail, pointing to related issues.

## Development setup

```bash
git clone https://github.com/Amaan9136/faceswap-live.git
cd faceswap-live
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt
python run_web.py
```

Then open `http://127.0.0.1:8000`. See the [README](README.md#-quick-start) for GPU
setup, model downloads, and platform notes.

## Making a change

1. **Fork** the repo and create a branch off `main`:
   `git checkout -b feature/short-description` or `fix/short-description`.
2. **Keep changes focused.** One logical change per pull request makes review much
   faster. Avoid bundling unrelated formatting changes with functional ones.
3. **Match the existing style.** This codebase doesn't use a heavy formatter/linter
   config yet, follow the conventions already present in the file you're editing
   (naming, typing, structure).
4. **Test locally.** There isn't a full automated test suite yet (see
   [issues](https://github.com/Amaan9136/faceswap-live/issues) if you'd like to help
   change that), so manually verify:
   - The web server starts cleanly (`python run_web.py`).
   - Image/video swap still works end-to-end.
   - If you touched `modules/realtime_camera.py` or the `/api/realtime/*` routes, start
     a live session with a webcam and confirm streaming/settings still work.
5. **Update docs** if you changed behavior, added an endpoint, or changed a config
   option — the README and/or `docs/` should stay accurate.
6. **Commit with a clear message.** Conventional prefixes are welcome but not required:
   `fix: correct queue drop logic in realtime_camera`.
7. **Open a pull request** against `main` using the PR template. Link any related issue
   (e.g. `Closes #12`).

## Pull request review

- A maintainer will review as soon as they're able — this is currently a
  single-maintainer project, so please be patient.
- You may be asked to make changes. That's a normal part of the process, not a
  rejection.
- Once approved, a maintainer will merge it.

## Reporting security issues

Please **do not** open a public issue for security vulnerabilities. Follow the process
in [SECURITY.md](SECURITY.md) instead.

## Responsible use

This project performs face swapping, including real-time webcam face swapping.
Contributions that primarily enable non-consensual impersonation, harassment, or
deception are out of scope, see [SECURITY.md](SECURITY.md#responsible-use) and the
upstream [Deep-Live-Cam](https://github.com/hacksider/Deep-Live-Cam) usage guidelines,
which this project also follows.

## License

By contributing, you agree that your contributions will be licensed under the
[GNU Affero General Public License v3.0](LICENSE), the same license that covers the
rest of the project.