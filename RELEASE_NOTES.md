# Tensile Workbench 1.0.5

- Fix elastic fits and yield calculations when recorded strain reverses during
  unloading. Select the original loading phase before sorting by strain, so
  unloading readings cannot be mistaken for elastic data.
- Apply the same separation to landmark shapes and work-hardening plots. Keep
  the full measured curve visible in the inspector and group curve review.
- When a landmark plot is unavailable, identify the specimen and reason without
  mixing in unrelated pointwise tail-fitting messages.

Use **Check for updates → Install update and restart** in the desktop app.
Saved analyses, specimen overrides, data and output folders are preserved.
