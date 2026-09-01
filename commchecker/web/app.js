/* CommChecker front end.
   Every value that comes back from the server is escaped before it reaches the
   page: previews are text lifted out of an untrusted PDF, so they are treated
   as text and never as markup. */
(function () {
  "use strict";

  var drop = document.getElementById("drop");
  var file = document.getElementById("file");
  var res  = document.getElementById("res");

  function esc(value) {
    if (value === null || value === undefined) return "";
    return String(value)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;")
      .replace(/'/g, "&#39;");
  }

  /* ---- events ---- */
  drop.addEventListener("click", function () { file.click(); });
  drop.addEventListener("keydown", function (e) {
    if (e.key === "Enter" || e.key === " ") { e.preventDefault(); file.click(); }
  });
  ["dragover", "dragenter"].forEach(function (name) {
    drop.addEventListener(name, function (e) { e.preventDefault(); drop.classList.add("over"); });
  });
  ["dragleave", "drop"].forEach(function (name) {
    drop.addEventListener(name, function (e) { e.preventDefault(); drop.classList.remove("over"); });
  });
  drop.addEventListener("drop", function (e) {
    if (e.dataTransfer && e.dataTransfer.files[0]) send(e.dataTransfer.files[0]);
  });
  file.addEventListener("change", function () {
    if (file.files[0]) send(file.files[0]);
  });

  /* ---- request ---- */
  function send(f) {
    res.innerHTML = '<p class="loading">Checking ' + esc(f.name) + "…</p>";
    var form = new FormData();
    form.append("file", f);
    fetch("verify", { method: "POST", body: form })
      .then(function (r) { return r.json(); })
      .then(render)
      .catch(function (err) {
        res.innerHTML =
          '<div class="card"><div class="banner fail"><div class="v">ERROR</div>' +
          '<div class="m">Could not reach the verifier: ' + esc(err.message) +
          "</div></div></div>";
      })
      .finally(function () { file.value = ""; });
  }

  /* ---- rendering ---- */
  function render(d) {
    /* Three presentations, not two. A re-saved file has to look different
       from an altered one, or people stop reading the difference. */
    var severity = d.severity || (d.verdict === "PASS" ? "none" : "alert");
    var tone = severity === "none" ? "pass"
             : severity === "notice" ? "notice"
             : "fail";
    var headline = d.headline || (d.verdict === "PASS" ? "PASS" : "FAIL");

    var html = '<div class="card">';

    html +=
      '<div class="banner ' + tone + '">' +
      '<div class="v">' + esc(headline) + "</div>" +
      '<div class="m">' + esc(d.message) + "</div></div>";

    if (severity === "notice") {
      html +=
        '<div class="nextstep">What to do: ask for the original sealed ' +
        "export and file that instead. This is routine — a PDF that gets " +
        "opened and saved again is rewritten, which breaks the seal without " +
        "changing a word.</div>";
    }

    html += renderFindings(d.records);
    html += renderChecks(d.checks);
    html += renderFacts(d);
    html += renderWarnings(d.warnings);

    html += "</div>";
    res.innerHTML = html;
  }

  /* The headline: which specific records changed. */
  function renderFindings(records) {
    if (!records) return "";
    var items = []
      .concat(records.changed || [])
      .concat(records.missing || [])
      .concat(records.added || []);
    if (!items.length) return "";

    var html = '<div class="findings"><h2>What changed</h2>';
    items.forEach(function (item) {
      var meta = [item.sent_utc, item.direction, item.party]
        .filter(Boolean).map(esc).join(" &middot; ");
      html += '<div class="finding">';
      html += '<div class="id">Record ' + esc(item.id) +
              (item.page ? " &middot; page " + esc(item.page) : "") + "</div>";
      if (meta) html += '<div class="meta">' + meta + "</div>";
      html += '<div class="what">' + esc(item.what_happened) + "</div>";

      if (item.sealed_text || item.current_text) {
        html += '<div class="diff">';
        if (item.sealed_text) {
          html += '<div class="was"><span class="lbl">When sealed</span>' +
                  esc(item.sealed_text) + "</div>";
        }
        if (item.current_text) {
          html += '<div class="now"><span class="lbl">In this file now</span>' +
                  esc(item.current_text) + "</div>";
        }
        html += "</div>";
      }
      html += "</div>";
    });
    return html + "</div>";
  }

  function renderChecks(checks) {
    if (!checks || !checks.length) return "";
    var html = '<div class="checks">';
    checks.forEach(function (c) {
      var cls, glyph;
      if (c.ok === true)       { cls = "ok";      glyph = "✓"; }
      else if (c.ok === false) { cls = "no";      glyph = "×"; }
      else                     { cls = "unknown"; glyph = "?"; }
      html +=
        '<div class="row"><span class="dot ' + cls + '">' + glyph + "</span>" +
        '<div><div class="t">' + esc(c.check) + "</div>" +
        '<div class="d">' + esc(c.detail) + "</div></div></div>";
    });
    return html + "</div>";
  }

  function renderFacts(d) {
    var rows = [];

    if (d.records && d.records.manifest_present) {
      rows.push([
        "Records checked",
        d.records.matched_count + " of " + d.records.record_count_sealed + " match",
      ]);
    }

    if (d.timestamp && d.timestamp.present) {
      var when = d.timestamp.time_utc || "unknown time";
      var who = d.timestamp.trusted
        ? "trusted authority"
        : "authority not verified";
      rows.push(["Trusted timestamp", when + " (" + who + ")"]);
      if (d.timestamp.authority) rows.push(["Timestamp authority", d.timestamp.authority]);
    } else {
      rows.push(["Trusted timestamp", "none on this seal"]);
    }

    if (d.seal && d.seal.signer && d.seal.signer.subject) {
      rows.push(["Sealed by", d.seal.signer.subject]);
      if (d.seal.signer.issuer) rows.push(["Certificate issued by", d.seal.signer.issuer]);
    }

    var html = '<div class="facts">';
    rows.forEach(function (r) {
      html += '<div class="fact"><span class="k">' + esc(r[0]) +
              '</span><span class="v">' + esc(r[1]) + "</span></div>";
    });
    if (d.file_sha256) {
      html += '<div class="fact"><span class="k">File SHA-256</span>' +
              '<span class="v mono">' + esc(d.file_sha256) + "</span></div>";
    }
    return html + "</div>";
  }

  function renderWarnings(warnings) {
    if (!warnings || !warnings.length) return "";
    var html = '<div class="warnings">';
    warnings.forEach(function (w) {
      html += '<div class="w">! ' + esc(w) + "</div>";
    });
    return html + "</div>";
  }

  /* Show which certificate world the server is running in, so a demo is never
     mistaken for production. */
  fetch("config")
    .then(function (r) { return r.json(); })
    .then(function (c) {
      var line = document.getElementById("modeline");
      if (!line) return;
      line.textContent =
        c.mode === "production"
          ? "Production mode · seals verified against configured trust roots"
          : "Demo mode · self-signed certificate, for testing only";
    })
    .catch(function () { /* the badge is cosmetic; ignore failures */ });
})();
