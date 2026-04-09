(function() {
    var lastTs = null;
    var polling = null;

    function check() {
        var xhr = new XMLHttpRequest();
        xhr.open('GET', '/_build_ts?' + Date.now(), true);
        xhr.timeout = 2000;
        xhr.onreadystatechange = function() {
            if (xhr.readyState !== 4 || xhr.status !== 200) return;
            var newTs = xhr.responseText.trim();
            if (!newTs) return;
            if (lastTs === null) {
                lastTs = newTs;
                console.log('[docs-reload] Initial build timestamp:', lastTs);
                return;
            }
            if (newTs !== lastTs) {
                console.log('[docs-reload] Build changed:', lastTs, '->', newTs, '-- reloading');
                location.reload();
            }
        };
        xhr.onerror = function() {};
        xhr.send();
    }

    function start() {
        if (!polling) {
            polling = setInterval(check, 3000);
            console.log('[docs-reload] Watching for changes...');
        }
    }

    function stop() {
        if (polling) {
            clearInterval(polling);
            polling = null;
            console.log('[docs-reload] Paused (tab hidden)');
        }
    }

    document.addEventListener('visibilitychange', function() {
        document.hidden ? stop() : start();
    });

    start();
})();
