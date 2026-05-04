# Docker Image Security Scan Report

**Date:** 2026-04-07
**Scanner:** Trivy
**Severity:** HIGH, CRITICAL

---

## Executive Summary

| Status | Value |
|--------|-------|
| CRITICAL | **0** ✅ |
| HIGH | 32 |
| MEDIUM | 33 |
| **Total** | **65** |

**Recommendation:** System can proceed to production with **monitoring and mitigations** in place for known unfixed vulnerabilities.

---

## Vulnerability Summary by Image

| Image | OS | CRITICAL | HIGH | MEDIUM | Total |
|-------|----|:--------:|:----:|:------:|:-----:|
| `ghcr.io/berriai/litellm:v1.83.4-nightly` | wolfi | 0 | 4 | 0 | 4 |
| `tstation-ai:latest` | alpine 3.23.3 | 0 | 2 | 18 | 20 |
| `tstation-ui-demo:latest` | alpine 3.23.3 | 0 | 6 | 4 | 10 |
| `nginx:alpine` | alpine 3.23.3 | 0 | 3 | 1 | 4 |
| `redis` | debian 13.4 | 0 | 5 | 10 | 15 |
| `qdrant/qdrant:latest` | debian 13.4 | 0 | 12 | 0 | 12 |

---

## Detailed Findings

### 1. ghcr.io/berriai/litellm:v1.83.4-nightly

**Status:** ✅ CRITICAL FIXED

| CVE | Severity | Package | Fix Version | Status |
|-----|----------|---------|-------------|--------|
| CVE-2026-33671 | HIGH | picomatch | 4.0.4 | Fixed |
| CVE-2025-67221 | HIGH | orjson | 3.11.6 | Fixed |
| CVE-2026-24486 | HIGH | python-multipart | 0.0.22 | Available |

---

### 2. tstation-ai:latest

| CVE | Severity | Package | Fix Version | Status |
|-----|----------|---------|-------------|--------|
| CVE-2026-22184 | HIGH | zlib | 1.3.2-r0 | Available |
| CVE-2025-7647 | HIGH | llama-index-core | 0.13.0 | Available |
| CVE-2025-55197 | MEDIUM | pypdf | 6.0.0 | Available |
| CVE-2025-62707 | MEDIUM | pypdf | 6.1.3 | Available |
| + 14 more MEDIUM | MEDIUM | pypdf, requests | 6.9.2+ | Available |

---

### 3. tstation-ui-demo:latest

| CVE | Severity | Package | Fix Version | Status |
|-----|----------|---------|-------------|--------|
| CVE-2026-22184 | HIGH | zlib | 1.3.2-r0 | Available |
| CVE-2026-23949 | HIGH | jaraco.context | 6.1.0 | Available |
| CVE-2025-47273 | HIGH | setuptools | 78.1.1 | Available |
| CVE-2026-24049 | HIGH | wheel | 0.46.2 | Available |
| CVE-2026-31958 | MEDIUM | tornado | 6.5.5 | Available |
| CVE-2025-8869 | MEDIUM | pip | 25.3 | Available |

---

### 4. nginx:alpine

| CVE | Severity | Package | Fix Version | Status |
|-----|----------|---------|-------------|--------|
| CVE-2026-33416 | HIGH | libpng | 1.6.56-r0 | Available |
| CVE-2026-33636 | HIGH | libpng | - | No fix |
| CVE-2026-22184 | HIGH | zlib | 1.3.2-r0 | Available |
| CVE-2026-27171 | MEDIUM | zlib | - | No fix |

---

### 5. redis

| CVE | Severity | Package | Fix Version | Status |
|-----|----------|---------|-------------|--------|
| CVE-2026-29111 | HIGH | libsystemd0 | - | **NO FIX** |
| CVE-2025-69720 | HIGH | ncurses | - | No fix |
| CVE-2026-4046 | MEDIUM | glibc | - | No fix |
| CVE-2026-4437 | MEDIUM | glibc | - | No fix |
| CVE-2026-4438 | MEDIUM | glibc | - | No fix |

---

### 6. qdrant/qdrant:latest

| CVE | Severity | Package | Fix Version | Status |
|-----|----------|---------|-------------|--------|
| CVE-2026-29111 | HIGH | libsystemd0 | - | **NO FIX** |
| CVE-2025-69720 | HIGH | ncurses | - | No fix |
| CVE-2026-4800 | HIGH | lodash | 4.18.0 | Available |
| CVE-2026-33671 | HIGH | picomatch | 4.0.4 | Available |
| CVE-2026-39363 | HIGH | vite | 6.4.2 | Available |
| GHSA-394x-vwmw-crm3 | HIGH | aws-lc-sys | 0.39.0 | Available |
| GHSA-9f94-5g5w-gf6r | HIGH | aws-lc-sys | - | No fix |
| CVE-2026-31812 | HIGH | quinn-proto | 0.11.14 | Available |

---

## Known Unfixed Vulnerabilities

| CVE | Image | Risk | Mitigation |
|-----|-------|------|------------|
| **CVE-2026-29111** | redis, qdrant | Arbitrary code execution via systemd IPC | Network isolation; non-root execution |
| CVE-2026-33636 | nginx | Info disclosure + DoS via libpng | Monitor for patch |
| CVE-2026-27171 | all | DoS via zlib CRC32 | Monitor for patch |
| CVE-2026-4437/4438 | redis | DNS spoofing via glibc | Use encrypted DNS |
| CVE-2026-34743 | redis | DoS via xz | Monitor for patch |
| GHSA-9f94-5g5w-gf6r | qdrant | CRL scope check error | Monitor for patch |

---

## Production Readiness: CONDITIONALLY APPROVED

### Required Mitigations

1. **Network Isolation** - Isolate redis and qdrant in private network
2. **Non-root Execution** - Ensure containers run as non-root user
3. **Monitoring** - Set up alerts for new CVE disclosures
4. **Patch Management** - Subscribe to security updates for all images

### High Priority Fixes

| Priority | Action | Owner |
|----------|--------|-------|
| P1 | Upgrade tstation-ai base image to alpine 3.23.4+ | DevOps |
| P1 | Upgrade llama-index-core to 0.13.0+ | DevOps |
| P2 | Upgrade nginx:alpine to fixed version | DevOps |
| P2 | Upgrade tstation-ui-demo packages | DevOps |

### Long-term

- Monitor upstream for **CVE-2026-29111** (systemd) fix in debian 13.4
- Consider alternative base images if systemd CVE remains unfixed

---

## Conclusion

**CRITICAL vulnerabilities: 0** ✅

The system has no critical vulnerabilities and can proceed to production with the mitigations and monitoring controls described above.

The most significant remaining risk is **CVE-2026-29111** (systemd RCE) affecting redis and qdrant images, which has no available fix yet. This risk should be mitigated through network isolation and container security best practices.
