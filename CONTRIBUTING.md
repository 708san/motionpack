# Contributing to MotionPack (pre-alpha)

MotionPack is an experimental public repository. The format and APIs are unstable.

- Before implementing a change, open an issue describing the scope and acceptance criteria.
- Work on a branch and submit a small pull request. Do not push directly to `main`.
- Describe testing, compatibility impact, security risks, and visual changes in the PR.
- Do not commit credentials, personal/source images without permission, or third-party assets without verified rights.
- Do not report security vulnerabilities with exploit details in public issues; see [SECURITY.md](SECURITY.md).
- A license and contributor policy have not yet been selected. Discuss the terms with the maintainer before sending substantial code contributions.

Suggested local baseline:

```bash
python tools/validate.py examples/robot_ik_demo
python tools/validate.py examples/robot_demo
python tools/package.py examples/robot_ik_demo --out /tmp/motionpack_build
node tests/ik_test.js
node tests/runtime_ik_smoke.js
node tests/runtime_smoke.js
python -m unittest discover -s tests -v
```