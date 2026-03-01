/**
 * Switch the Molstar viewer to Selection Mode after a structure loads.
 *
 * In Selection Mode, clicking a residue in the 3D viewer creates a
 * highlight/selection without changing the representation or colors.
 * This preserves the pink target-residue coloring set by the Python app.
 */
(function () {
    "use strict";

    function getPluginFromContainer(container) {
        // Navigate the React fiber tree to find the Dash component instance
        // that holds the RCSB Molstar Viewer, then access its plugin.
        var key = Object.keys(container).find(function (k) {
            return k.startsWith("__reactFiber$") || k.startsWith("__reactInternalInstance$");
        });
        if (!key) return null;

        var fiber = container[key];
        var current = fiber;
        while (current) {
            if (current.stateNode && current.stateNode.viewer && current.stateNode.viewer._plugin) {
                return current.stateNode.viewer._plugin;
            }
            current = current.return;
        }
        return null;
    }

    function enableSelectionMode() {
        var container = document.getElementById("molstar-viewer");
        if (!container) return;

        var plugin = getPluginFromContainer(container);
        if (plugin && !plugin.selectionMode) {
            plugin.selectionMode = true;
        }
    }

    // Observe the structure-container div. When its style changes from
    // display:none to display:block, the structure has loaded — enable
    // selection mode after a short delay to let Molstar finish rendering.
    var observer = new MutationObserver(function (mutations) {
        for (var i = 0; i < mutations.length; i++) {
            var m = mutations[i];
            if (m.type === "attributes" && m.attributeName === "style") {
                var el = m.target;
                if (el.id === "structure-container" && el.style.display !== "none") {
                    // Molstar needs a moment to finish initializing after data loads
                    setTimeout(enableSelectionMode, 1500);
                }
            }
        }
    });

    // Start observing once the DOM is ready
    function init() {
        observer.observe(document.body, {
            attributes: true,
            attributeFilter: ["style"],
            subtree: true,
        });
    }

    if (document.readyState === "loading") {
        document.addEventListener("DOMContentLoaded", init);
    } else {
        init();
    }
})();
