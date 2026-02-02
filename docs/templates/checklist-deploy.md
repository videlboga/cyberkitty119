---
title: "Deployment checklist"
author: "release-engineer"
date: 2026-01-23
status: Draft
tags: [deploy, checklist]
---

# Deployment checklist

## Before deploy
- [ ] All tests green
- [ ] DB migrations reviewed
- [ ] ADR/Runbook updated if infra changes

## During deploy
- [ ] Canary deploy to 10%
- [ ] Monitor errors and queue lengths

## After deploy
- [ ] Smoke tests passed
- [ ] Metrics stable for 30m
