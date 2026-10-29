import assert from "node:assert/strict";
import { test } from "node:test";

import { enableFold, NARROW, narrowStart } from "../../src/archview/ui/narrow.js";

// Just enough of the DOM for enableFold: children in order, moved by append and insertBefore.
function el(name) {
  const node = {
    name, parentElement: null, children: [], listeners: {},
    get nextElementSibling() {
      const siblings = node.parentElement?.children || [];
      return siblings[siblings.indexOf(node) + 1] || null;
    },
    get lastElementChild() { return node.children.at(-1) || null; },
    append(child) { node.insertBefore(child, null); },
    insertBefore(child, before) {
      child.parentElement?.children.splice(child.parentElement.children.indexOf(child), 1);
      const at = before ? node.children.indexOf(before) : node.children.length;
      node.children.splice(at, 0, child);
      child.parentElement = node;
    },
    addEventListener(type, fn) { (node.listeners[type] ||= []).push(fn); },
    fire(type, e) { for (const fn of node.listeners[type] || []) fn(e); },
  };
  return node;
}

function media(matches) {
  const list = el("media");
  list.matches = matches;
  list.change = (now) => { list.matches = now; list.fire("change", { matches: now }); };
  return list;
}

// The toolbar: up, the fold, rules, and the ⋯ menu with its body.
function toolbar() {
  const tools = el("tools");
  const [up, fold, rules, more, summary, body] = ["up", "fold", "rules", "more", "summary", "body"].map(el);
  for (const child of [up, fold, rules, more]) tools.append(child);
  more.append(summary);
  more.append(body);
  more.hidden = true;
  more.open = false;
  return { tools, fold, more, body };
}
const names = (node) => node.children.map((c) => c.name);

test("the breakpoint is the one app.css uses", () => {
  assert.equal(NARROW, "(max-width: 760px)");
});

test("on a narrow screen the controls move into the menu and the menu shows", () => {
  const { tools, fold, more, body } = toolbar();
  enableFold(fold, more, media(true));
  assert.deepEqual(names(body), ["fold"]);
  assert.deepEqual(names(tools), ["up", "rules", "more"]);
  assert.equal(more.hidden, false);
});

test("on a wide screen they stay put and the menu is hidden", () => {
  const { tools, fold, more } = toolbar();
  enableFold(fold, more, media(false));
  assert.deepEqual(names(tools), ["up", "fold", "rules", "more"]);
  assert.equal(more.hidden, true);
});

test("widening puts them back where they were and closes the menu", () => {
  const { tools, fold, more, body } = toolbar();
  const screen = media(true);
  enableFold(fold, more, screen);
  more.open = true;
  screen.change(false);
  assert.deepEqual(names(tools), ["up", "fold", "rules", "more"]);
  assert.deepEqual(names(body), []);
  assert.equal(more.hidden, true);
  assert.equal(more.open, false);
  screen.change(true);
  assert.deepEqual(names(body), ["fold"], "and narrowing again folds them again");
});

test("a button inside the menu closes it; a checkbox does not", () => {
  const { fold, more } = toolbar();
  enableFold(fold, more, media(true));
  more.open = true;
  more.fire("click", { target: { closest: () => null } });
  assert.equal(more.open, true, "a checkbox in View");
  more.fire("click", { target: { closest: (s) => (s === "button" ? {} : null) } });
  assert.equal(more.open, false, "Find, a zoom button, an export");
});

test("a narrow start closes the drawer and the legend and holds what was saved", () => {
  const saved = { tree: true, legend: true, colour: "zone" };
  const { options, held } = narrowStart(saved);
  assert.deepEqual(options, { tree: false, legend: false, colour: "zone" });
  assert.deepEqual(held, { tree: true, legend: true });
  assert.deepEqual(saved, { tree: true, legend: true, colour: "zone" }, "the saved options are not changed");
});
