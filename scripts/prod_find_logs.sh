#!/bin/bash
find /opt/policy-tracker -name 'fed-doj-news-rerun*.log' -mmin -30 2>/dev/null | head -5
find /opt/policy-tracker -name '*.log' -mmin -30 2>/dev/null | head -10
