# Third-party components

TesterBot itself is MIT licensed (see `LICENSE`). It ships two vendored
components, each under its own licence. Both licences travel with the code in
`testerbot/vendor/`.

| Component | Used for | Licence | Full text |
|---|---|---|---|
| [axe-core](https://github.com/dequelabs/axe-core) by Deque Systems | The WCAG 2.1 A/AA accessibility audit that runs on every crawled page | Mozilla Public License 2.0 | `testerbot/vendor/axe-core-LICENSE.txt` |
| Technology fingerprints | Detecting the frameworks, CDNs, analytics and CMSs a site is built from | MIT | `testerbot/vendor/techfp-LICENSE.txt` |

Neither component is modified. They are bundled rather than downloaded at run
time so that TesterBot works with no internet connection and produces the same
result on every machine.

At run time TesterBot also drives **Chromium** through
[Playwright](https://playwright.dev) (Apache-2.0). Playwright is installed by
`install.sh` from PyPI and is not vendored here.
