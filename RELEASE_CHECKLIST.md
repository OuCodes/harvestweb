# Release Checklist

This checklist is optimized for `webharvest` using GitHub Actions + trusted publishing.

## 1. One-time account setup

PyPI and TestPyPI are separate services. Create accounts on both:

- PyPI: https://pypi.org/account/register/
- TestPyPI: https://test.pypi.org/account/register/

Use the same owner identity on both if you want, but you still need to register twice.

Before publishing:

- verify your email on both services
- enable two-factor authentication on both services
- keep the username/owner identity consistent with `OuCodes`

## 2. One-time GitHub repo setup

Repository:

- GitHub repo: `OuCodes/webharvest`
- Release workflow file: `.github/workflows/release.yml`
- TestPyPI environment name: `testpypi`
- PyPI environment name: `pypi`

Recommended GitHub setup:

- keep `testpypi` unprotected for faster dry runs
- optionally add approval rules to `pypi`
- no API token secrets are needed when trusted publishing is configured correctly

## 3. One-time trusted publisher setup on TestPyPI

After creating your TestPyPI account:

1. sign in to TestPyPI
2. add a **pending publisher** for project `webharvest`
3. choose **GitHub Actions** as the publisher type
4. use these values:
   - project name: `webharvest`
   - owner: `OuCodes`
   - repository name: `webharvest`
   - workflow name: `release.yml`
   - environment name: `testpypi`

This lets the GitHub Actions workflow publish without a long-lived token.

## 4. One-time trusted publisher setup on PyPI

Repeat the same process on PyPI:

1. sign in to PyPI
2. add a **pending publisher** for project `webharvest`
3. choose **GitHub Actions** as the publisher type
4. use these values:
   - project name: `webharvest`
   - owner: `OuCodes`
   - repository name: `webharvest`
   - workflow name: `release.yml`
   - environment name: `pypi`

Do this before the first real release.

## 5. Before every release

### Product checks

- confirm the package name is still right: `webharvest`
- confirm the version in `pyproject.toml`
- update `CHANGELOG.md`
- scan for PII or repo-local residue
- confirm README examples still work

### Local verification

Run:

```bash
./.venv/bin/python -m pytest
./.venv/bin/python -m build
./.venv/bin/python -m webharvest --help
```

Optional extra residue scan:

```bash
rg -n "growthkit|eskiin|/Users/|client_secret|token\.pickle|agent@|mac-field" . --glob '!/.git/**' --glob '!.venv/**'
```

## 6. First TestPyPI release

Use TestPyPI before the first real PyPI release.

### Trigger the workflow

The current release workflow publishes to TestPyPI when run manually:

1. open GitHub Actions
2. select the `Release` workflow
3. click **Run workflow**
4. run it from `main`

That workflow will:

- build the sdist and wheel
- upload artifacts
- publish to TestPyPI through OIDC trusted publishing

### Verify the package on TestPyPI

After the workflow succeeds:

1. visit the TestPyPI project page
2. confirm metadata renders correctly
3. test install from TestPyPI:

```bash
python3 -m venv /tmp/webharvest-test
/tmp/webharvest-test/bin/python -m pip install --upgrade pip
/tmp/webharvest-test/bin/python -m pip install \
  --index-url https://test.pypi.org/simple/ \
  --extra-index-url https://pypi.org/simple \
  webharvest
/tmp/webharvest-test/bin/python -m webharvest --help
```

Why `--extra-index-url` matters:

- TestPyPI may not host all transitive dependencies
- pip can pull shared dependencies from real PyPI

## 7. Real PyPI release

Once TestPyPI looks good:

1. update `CHANGELOG.md` for the release
2. commit the release prep
3. tag the version:

```bash
git tag v0.1.0
git push origin v0.1.0
```

4. the same `Release` workflow will publish to PyPI automatically on the tag push

## 8. After publishing

- verify the project page on PyPI
- test `pip install webharvest`
- test `python -m webharvest --help`
- create a GitHub Release if you want human-readable release notes
- move the released notes from `Unreleased` in `CHANGELOG.md` into a versioned section

## 9. If publishing fails

Common failure points:

- PyPI/TestPyPI account not created yet
- email not verified
- 2FA not enabled
- pending publisher missing or misconfigured
- workflow filename mismatch (`release.yml`)
- environment name mismatch (`testpypi` or `pypi`)
- package name conflict on the registry
- version already published

## 10. Current release wiring summary

Current package details:

- package name: `webharvest`
- import package: `webharvest`
- console script: `webharvest`
- current version: `0.1.0`
- release workflow: `.github/workflows/release.yml`
