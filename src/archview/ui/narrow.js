// The viewer on a phone's width (V22): the toolbar keeps one row by folding its
// secondary controls into a ⋯ menu, and the diagram comes first.

export const NARROW = "(max-width: 760px)";  // the breakpoint app.css uses too

// Moves `fold`, the container of secondary controls, into the menu body (the last
// child of `more`, a <details>) while `media` matches, and back where it was when it
// stops. The controls move rather than being copied, so their handlers stay put.
export function enableFold(fold, more, media) {
  const home = fold.parentElement;
  const before = fold.nextElementSibling;  // the Rules button, which never moves
  const place = (narrow) => {
    if (narrow) more.lastElementChild.append(fold);
    else home.insertBefore(fold, before);
    more.hidden = !narrow;
    if (!narrow) more.open = false;
  };
  place(media.matches);
  media.addEventListener("change", (e) => place(e.matches));
  // A button's action is done in one tap, so the menu gets out of the way; the
  // checkboxes and radios in View keep it open for the next choice.
  more.addEventListener("click", (e) => {
    if (e.target.closest("button")) more.open = false;
  });
}

// A narrow start shows the diagram alone: the drawer and the legend start closed.
// `held` is what was saved for them, so saving from here does not close them for the
// next wide window.
export function narrowStart(options) {
  return {
    options: { ...options, tree: false, legend: false },
    held: { tree: options.tree, legend: options.legend },
  };
}
