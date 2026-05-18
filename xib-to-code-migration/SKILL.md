---
name: xib-to-code-migration
description: Convert iOS/macOS xib or nib-backed UI to pure code and remove Interface Builder dependencies. Use when the user asks to migrate or delete xib/nib files, replace loadNibNamed/UINib/nibWithNibName/registerNib usage, convert UIKit/AppKit views/controllers/cells to code, or clean Xcode project references after xib removal.
---

# XIB to Code Migration

## 前置流程

- 先认真阅读仓库根 `AGENTS.md` 并严格遵守与其相关的规则及流程。
- If the repo rules require a feature SPEC, docs map, approval step, or validation flow, follow that repo-specific process before editing.
- Do not create duplicate AI instruction files or project docs unless the repo rules explicitly require them.

## Workflow

1. **Discover all coupling first**
   - Locate the target `.xib`/`.nib`, owner class, companion source files, creation points, registration points, and Xcode project references.
   - Search for the xib name plus `loadNibNamed`, `UINib`, `nibWithNibName`, `registerNib`, `register(_:forCellReuseIdentifier:)`, and reuse identifiers.
   - For shared cells/views, identify every registration and dequeue path before deleting the xib.

2. **Pass 1: restore the xib 1:1 in code**
   - Recreate the view hierarchy, constraints, colors, fonts, images, content modes, visibility, alpha, corner radius, borders, and event wiring.
   - Convert `IBOutlet` to normal stored properties and `IBAction` to explicit target/action or equivalent code hooks.
   - Preserve the module's existing language and layout style, such as Objective-C + Masonry or Swift + SnapKit.
   - Preserve safe area semantics. If the xib constrained to safe area, add a short comment near the translated constraint.

3. **Pass 2: calibrate against old runtime logic**
   - Re-read the pre-migration code in the same file and its immediate caller.
   - Check `awakeFromNib`, `setModel`, `setHelpModel`, `layoutSubviews`, data binding, state changes, RTL branches, localization, and async refreshes.
   - If old code overwrote xib initial constants or properties, use the actual runtime value in both initialization and update paths.
   - Do not blindly keep XML constants when old code made them transient.

4. **Comment runtime corrections**
   - When code intentionally differs from the xib initial value because of old runtime logic, add a concise comment at the changed code.
   - The comment must name the xib initial value, the old code path or reason, and the final runtime value.
   - Do not add noisy comments for direct 1:1 translations.

5. **Remove Interface Builder dependencies**
   - Replace nib loading/registration with pure-code construction or class registration.
   - Delete the xib file.
   - Remove the xib from `project.pbxproj`: `PBXBuildFile`, `PBXFileReference`, group children, and Resources build phase.
   - Keep unrelated project file changes intact.

## Guardrails

- Preserve business behavior, network requests, routing, analytics events, notification behavior, masks, animations, RTL behavior, localization, async callbacks, empty/failure states, and repeated-entry behavior.
- Do not redesign, restyle, re-architect, rename public APIs, or refactor unrelated code.
- Respect dirty worktrees: never revert user changes, and report unrelated blockers separately.
- Use structured parsers or project tooling when available; otherwise edit `project.pbxproj` narrowly and verify it afterwards.

## Validation

- Search for residual xib names and nib APIs in the target scope and project file.
- Run `plutil -lint` on `project.pbxproj` when it changed.
- Run scoped `git diff --check` on touched paths.
- Build or test with the repo's preferred Xcode workflow when feasible.
- Report any full-worktree check failures caused by unrelated files separately.
