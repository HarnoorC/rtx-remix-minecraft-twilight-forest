# Security

NVIDIA is dedicated to the security and trust of our software products and
services, including all source code repositories managed through our
organization.

If you need to report a security issue, please use the appropriate contact
points outlined below. Please do not report security vulnerabilities through
GitHub issues.

## Reporting Potential Security Vulnerability in an NVIDIA Product

To report a potential security vulnerability in any NVIDIA product:

- Web: [Security Vulnerability Submission Form](https://www.nvidia.com/object/submit-security-vulnerability.html)
- E-Mail: psirt@nvidia.com
  - We encourage you to use the following PGP key for secure email
    communication: [NVIDIA public PGP Key for communication](https://www.nvidia.com/en-us/security/pgp-key)
  - Please include the following information:
    - Product or component name: **RTX Remix for Minecraft**, and the mod
      file name from the `mods` folder, which carries the version and the
      commit it was built from
    - Type of vulnerability and its impact
    - Instructions to reproduce the vulnerability, and proof-of-concept or
      exploit code if you have it

While NVIDIA currently does not have a bug bounty program, we do offer
acknowledgement when an externally reported security issue is addressed under
our coordinated vulnerability disclosure policy. Please visit our
[Product Security Incident Response Team (PSIRT)](https://www.nvidia.com/en-us/security/psirt-policies/)
policies page for more information.

## Which Project

This repository is the Minecraft mod: the code that reads Minecraft state and
hands it to the RTX Remix runtime, the settings screen, the gameplay-driven
lighting profiles, and the Windows installer under `packaging/`. A crash, a
driver fault, or a memory-safety problem inside the runtime itself belongs to
[dxvk-remix](https://github.com/NVIDIAGameWorks/dxvk-remix); if the same
problem reproduces in another Remix title, it is a runtime issue. Either way
the reporting channels above are the same, and a report naming the wrong
component is routed rather than dropped.

## NVIDIA Product Security

For all security-related concerns, please visit NVIDIA's Product Security
portal at https://www.nvidia.com/en-us/security
