// Swipe-right actions for list rows.
//
// A row with class "swipe-row" and data-swipe-right="<selector>" can be
// dragged to the right; past the threshold it "clicks" the element matching
// the selector inside the row, so a swipe and a tap on that button share one
// code path (and the button always works without swiping).
//
// Delegated listeners on document, so rows swapped in by htmx just work.
// Touch and pen only (a mouse uses the buttons). Vertical scrolling stays
// native (CSS touch-action: pan-y); gestures starting at a screen edge are
// ignored so they don't fight the browser's back-swipe.
(function () {
    if (window.swipeActionsLoaded) {
        return;
    }
    window.swipeActionsLoaded = true;

    var EDGE_PX = 24;
    var LOCK_PX = 10;
    var MIN_PX = 80;
    var FRACTION = 0.35;
    var state = null;

    function reset(row) {
        row.classList.remove("is-swiping", "is-swipe-armed");
        row.style.removeProperty("--swipe-x");
        state = null;
    }

    function threshold(row) {
        return Math.max(MIN_PX, row.offsetWidth * FRACTION);
    }

    document.addEventListener("pointerdown", function (event) {
        if (event.pointerType === "mouse" || !event.isPrimary) {
            return;
        }
        var target = event.target;
        var row = target.closest && target.closest(".swipe-row[data-swipe-right]");
        if (!row || target.closest("button, a, input, select, textarea, label")) {
            return;
        }
        if (event.clientX < EDGE_PX || event.clientX > window.innerWidth - EDGE_PX) {
            return;
        }
        state = {
            row: row,
            id: event.pointerId,
            x: event.clientX,
            y: event.clientY,
            locked: false,
            dx: 0,
        };
    });

    document.addEventListener("pointermove", function (event) {
        if (!state || event.pointerId !== state.id) {
            return;
        }
        var dx = event.clientX - state.x;
        var dy = event.clientY - state.y;
        if (!state.locked) {
            if (Math.abs(dy) > LOCK_PX && Math.abs(dy) >= Math.abs(dx)) {
                state = null; // a vertical scroll, not ours
                return;
            }
            if (Math.abs(dx) <= LOCK_PX || Math.abs(dx) < 1.5 * Math.abs(dy)) {
                return;
            }
            state.locked = true;
            state.row.classList.add("is-swiping");
        }
        state.dx = Math.max(0, dx); // right only
        state.row.style.setProperty("--swipe-x", state.dx + "px");
        state.row.classList.toggle("is-swipe-armed", state.dx >= threshold(state.row));
    });

    function finish(event) {
        if (!state || event.pointerId !== state.id) {
            return;
        }
        var row = state.row;
        var fire = state.locked && state.dx >= threshold(row) && event.type === "pointerup";
        reset(row);
        if (!fire) {
            return;
        }
        var button = row.querySelector(row.dataset.swipeRight);
        if (button) {
            if (navigator.vibrate) {
                navigator.vibrate(10);
            }
            button.click();
        }
    }

    document.addEventListener("pointerup", finish);
    document.addEventListener("pointercancel", finish);
})();
