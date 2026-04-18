# Security Policy

## Overview

Security is an important consideration for any software system.
This document describes how to responsibly report security vulnerabilities related to this repository.

If you discover a vulnerability or security concern, please follow the reporting process outlined below.

---

# Supported Versions

The following versions of the project are currently supported with security updates.

| Version                    | Supported |
| -------------------------- | --------- |
| Current main branch        | ✓         |
| Development branch (`dev`) | ✓         |
| Older releases             | ✗         |

Security fixes will be applied to the actively maintained branches of the project.

---

# Reporting a Vulnerability

If you discover a security vulnerability, **please do not open a public issue immediately**.

Instead, report the issue privately so it can be investigated and resolved before public disclosure.

When reporting a vulnerability, include:

* A description of the issue
* Steps to reproduce the vulnerability
* Any relevant logs or screenshots
* Potential impact if known

Example report structure:

```
Vulnerability Summary:
Short description of the issue.

Affected Components:
API / memory bridge / runtime / etc.

Steps to Reproduce:
1.
2.
3.

Expected Behavior:
What should happen.

Actual Behavior:
What happens instead.
```

---

# Responsible Disclosure

Once a vulnerability is reported:

1. The issue will be reviewed and validated.
2. A fix will be developed if necessary.
3. The fix may be released before public disclosure.
4. A public advisory may be issued describing the issue and the fix.

We ask reporters to allow reasonable time for investigation and resolution before publicly disclosing vulnerabilities.

---

# Security Considerations

Contributors should be mindful of security when modifying or extending the system.

Important areas include:

* API input validation
* authentication and authorization logic
* error handling behavior
* data persistence and memory systems
* external service integrations

Relevant documentation:

```
docs/governance/ERROR_HANDLING_POLICY.md
docs/interfaces/API_CONTRACTS.md
docs/interfaces/MEMORY_BRIDGE_CONTRACT.md
```

Changes that affect these areas should be carefully reviewed.

---

# Dependency Security

When adding new dependencies:

* Prefer well-maintained libraries
* Avoid unnecessary packages
* Keep dependencies updated

Security advisories from dependency maintainers should be monitored and addressed when relevant.

---

# Scope

This security policy applies to:

* core system runtime
* API interfaces
* memory bridge components
* supporting infrastructure within this repository

External services or third-party dependencies are outside the direct scope of this policy but should be used responsibly.

---

# Summary

If you discover a security issue:

* report it privately
* provide detailed reproduction steps
* allow time for investigation and remediation

Responsible reporting helps maintain the reliability and security of the system.
