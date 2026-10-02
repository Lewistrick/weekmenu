// Drag-to-reorder for lists (needs vendor/sortablejs/Sortable.min.js first).
//
// Any <ul data-sortable-url="..."> becomes sortable by dragging the
// .drag-handle in its rows. After a drop, the rows' data-id values are POSTed
// to that URL as ids=3,1,2. If saving fails (e.g. the page is stale), the
// page reloads to show the stored order.
(function () {
    function enable(root) {
        root.querySelectorAll("[data-sortable-url]").forEach(function (list) {
            if (list.dataset.sortableReady) {
                return;
            }
            list.dataset.sortableReady = "true";
            Sortable.create(list, {
                handle: ".drag-handle",
                animation: 150,
                ghostClass: "is-drag-ghost",
                onEnd: function (event) {
                    if (event.oldIndex === event.newIndex) {
                        return;
                    }
                    var ids = Array.prototype.map
                        .call(list.children, function (item) {
                            return item.dataset.id;
                        })
                        .filter(Boolean);
                    fetch(list.dataset.sortableUrl, {
                        method: "POST",
                        credentials: "same-origin",
                        headers: { "Content-Type": "application/x-www-form-urlencoded" },
                        body: new URLSearchParams({ ids: ids.join(",") }),
                    })
                        .then(function (response) {
                            if (!response.ok) {
                                window.location.reload();
                            }
                        })
                        .catch(function () {
                            window.location.reload();
                        });
                },
            });
        });
    }

    // Saving or deleting a row re-renders the whole page body via htmx, which
    // runs this file again: only the first run registers the listener.
    if (!window.sortableListsLoaded) {
        window.sortableListsLoaded = true;
        document.addEventListener("htmx:afterSettle", function (event) {
            enable(event.target);
        });
    }
    enable(document);
})();
