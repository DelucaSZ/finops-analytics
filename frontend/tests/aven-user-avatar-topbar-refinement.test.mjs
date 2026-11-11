import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import test from "node:test";
import { fileURLToPath } from "node:url";

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const read = (file) => fs.readFileSync(path.join(ROOT, file), "utf8");
const shell = read("components/app-shell/application-shell.tsx");
const styles = read("components/app-shell/app-shell.module.css");
const tokens = read("app/styles/tokens/components.css");
const feedback = read("components/ui/feedback.module.css");
const userControl = shell.split("function UserControl(")[1]?.split("function Topbar(")[0] ?? "";
const avatarRule = styles.match(/\.userTrigger \.userAvatar\[data-size="md"\] \{([^}]+)\}/)?.[1] ?? "";
const copyRule = styles.match(/\.userTriggerCopy \{([^}]+)\}/)?.[1] ?? "";

test("Topbar uses the existing initials-only Avatar without changing user data or logout", () => {
  assert.match(userControl, /<Avatar fallback=\{initials\} alt=\{identityLabel\} size="md" className=\{styles\.userAvatar\} \/>/);
  assert.match(shell, /function getInitials\(value: string\)/);
  assert.match(shell, /words\.slice\(0, 2\)/);
  assert.match(userControl, /onClick=\{\(\) => void onLogout\(\)\}/);
  assert.doesNotMatch(userControl, /<img\b|\bsrc=|type="file"/);
});

test("Topbar avatar is 36px square and cannot shrink into an oval", () => {
  assert.match(tokens, /--shell-user-avatar-size: calc\(var\(--space-8\) \+ var\(--space-1\)\)/);
  assert.match(avatarRule, /aspect-ratio: 1;/);
  assert.match(avatarRule, /block-size: var\(--shell-user-avatar-size\);/);
  assert.match(avatarRule, /inline-size: var\(--shell-user-avatar-size\);/);
  assert.match(avatarRule, /min-inline-size: var\(--shell-user-avatar-size\);/);
  assert.match(avatarRule, /flex: 0 0 var\(--shell-user-avatar-size\);/);
  assert.match(avatarRule, /border-radius: var\(--radius-full\);/);
  assert.match(styles, /\.userTrigger \.userAvatar > span \{\s*white-space: nowrap;/);
  assert.match(feedback, /\.avatar \{[\s\S]*?align-items: center;[\s\S]*?justify-content: center;/);
});

test("Long identity text truncates without compressing the avatar or chevron", () => {
  assert.match(copyRule, /flex: 1 1 auto;/);
  assert.match(copyRule, /min-inline-size: var\(--space-0\);/);
  assert.match(copyRule, /overflow: hidden;/);
  assert.match(styles, /\.userTriggerCopy strong,\s*\.userTriggerCopy small \{[^}]*text-overflow: ellipsis;/);
  assert.match(styles, /\.userTrigger > svg:last-child \{\s*flex-shrink: 0;/);
});

test("Avatar remains scoped to Topbar and responsive menu behavior is retained", () => {
  assert.match(styles, /@media \(max-width: 850px\)[\s\S]*?\.topbarControlLabel,\s*\.userTriggerCopy \{\s*display: none;/);
  assert.match(styles, /@media \(max-width: 620px\)[\s\S]*?\.userTrigger > svg:last-child \{\s*display: none;/);
  assert.match(userControl, /<DropdownMenu>/);
  assert.match(userControl, /<DropdownMenuTrigger/);
  assert.match(userControl, /<DropdownMenuContent/);
  assert.doesNotMatch(feedback, /userAvatar/);
});
