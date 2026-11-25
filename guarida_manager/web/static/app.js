(() => {
  "use strict";

  const state = {
    status: null,
    models: [],
    projects: [],
    sessions: [],
    memory: [],
    activeProjectId: null,
    activeSessionId: null,
    catalogFilter: "all",
    sending: false,
    astData: { nodos_ast: [], relaciones_ast: [], expansion: [] },
  };

  const $ = (id) => document.getElementById(id);

  function esc(str) {
    return String(str ?? "")
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;")
      .replace(/'/g, "&#39;");
  }

  function showToast(msg, tipo = "info") {
    const cont = $("toast-container");
    const el = document.createElement("div");
    el.className = `toast toast-${tipo}`;
    el.textContent = msg;
    cont.appendChild(el);
    setTimeout(() => {
      el.remove();
    }, 4200);
  }

  async function api(path, options = {}) {
    const opts = {
      headers: { "Content-Type": "application/json", ...(options.headers || {}) },
      ...options,
    };
    const resp = await fetch(path, opts);
    const data = await resp.json().catch(() => ({}));
    if (!resp.ok) {
      throw new Error(data.error || `Error HTTP ${resp.status}`);
    }
    return data;
  }

  function renderMarkdown(text) {
    const raw = String(text || "");
    const parts = raw.split(/```([a-zA-Z0-9_-]*)\n?([\s\S]*?)```/g);
    let html = "";
    for (let i = 0; i < parts.length; i += 3) {
      const prose = parts[i] || "";
      html += formatProse(prose);
      if (i + 2 < parts.length) {
        const lang = esc(parts[i + 1] || "code");
        const code = esc(parts[i + 2].replace(/\n$/, ""));
        html += `
          <div class="code-block-wrap">
            <div class="code-block-head">
              <span>${lang}</span>
              <button class="btn-link btn-copy-code" type="button">Copiar</button>
            </div>
            <pre><code>${code}</code></pre>
          </div>
        `;
      }
    }
    return html;
  }

  function formatProse(text) {
    const escaped = esc(text);
    const withInline = escaped
      .replace(/`([^`\n]+)`/g, "<code>$1</code>")
      .replace(/\*\*([^*\n]+)\*\*/g, "<strong>$1</strong>");
    const lines = withInline.split(/\r?\n/);
    const out = [];
    for (const line of lines) {
      const trimmed = line.trim();
      if (!trimmed) {
        out.push("<br/>");
      } else if (trimmed.startsWith("### ")) {
        out.push(`<p><strong>${trimmed.slice(4)}</strong></p>`);
      } else if (trimmed.startsWith("## ") || trimmed.startsWith("# ")) {
        out.push(`<p><strong>${trimmed.replace(/^#+\s*/, "")}</strong></p>`);
      } else if (trimmed.startsWith("- ")) {
        out.push(`<p>&bull; ${trimmed.slice(2)}</p>`);
      } else {
        out.push(`<p>${trimmed}</p>`);
      }
    }
    return out.join("");
  }

  function updateStatusUI(status) {
    state.status = status;
    const hw = status.hardware || {};
    const tel = status.telemetria || {};
    const srv = status.servidor || {};
    const tier = status.tier || {};
    const priv = status.privacidad || {};

    $("mini-cpu").innerHTML = `CPU <strong>${(tel.cpu_pct ?? 0).toFixed(0)}%</strong>`;
    $("mini-ram").innerHTML = `RAM <strong>${(tel.ram_usada_gb ?? 0).toFixed(1)}/${(tel.ram_total_gb ?? 0).toFixed(0)}G</strong>`;
    $("mini-vram").innerHTML = `VRAM <strong>${(tel.vram_usada_gb ?? 0).toFixed(1)}/${(tel.vram_total_gb ?? 0).toFixed(0)}G</strong>`;
    $("mini-temp").innerHTML = `TEMP <strong>${tel.temperatura_c != null ? tel.temperatura_c.toFixed(0) + "°C" : "--"}</strong>`;
    $("privacy-mode-label").textContent = priv.modo || "estandar";

    const activo = Boolean(srv.activo || srv.disponible_http);
    const pill = $("server-status-pill");
    const inspBadge = $("inspector-srv-badge");
    if (activo) {
      pill.className = "pill pill-active";
      pill.innerHTML = `<span class="dot dot-emerald"></span> ACTIVO${srv.port ? " :" + esc(srv.port) : ""}`;
      inspBadge.className = "badge badge-emerald";
      inspBadge.textContent = "ACTIVO";
      $("btn-stop-engine").disabled = false;
    } else {
      pill.className = "pill pill-muted";
      pill.innerHTML = `<span class="dot dot-muted"></span> DETENIDO`;
      inspBadge.className = "badge badge-muted";
      inspBadge.textContent = "DETENIDO";
      $("btn-stop-engine").disabled = true;
    }

    $("srv-model").textContent = srv.modelo_activo_id || (srv.modelo ? srv.modelo.split(/[\\/]/).pop() : "--");
    $("srv-endpoint").textContent = srv.base_url || "--";
    $("srv-pid").textContent = srv.pid ? `${srv.pid} (${srv.uptime_segundos || 0}s)` : "--";
    $("srv-ngl-ctx").textContent =
      srv.n_gpu_layers != null ? `ngl=${srv.n_gpu_layers} | c=${srv.ctx_size || "--"}` : "--";

    $("tel-cpu-cores").textContent = tel.nucleos_cpu ? `(${tel.nucleos_cpu})` : "";
    $("tel-cpu-val").textContent = `${(tel.cpu_pct ?? 0).toFixed(1)}%`;
    $("bar-cpu").style.width = `${Math.min(100, Math.max(0, tel.cpu_pct ?? 0))}%`;

    $("tel-ram-val").textContent = `${(tel.ram_usada_gb ?? 0).toFixed(1)} / ${(tel.ram_total_gb ?? 0).toFixed(1)} GB`;
    $("bar-ram").style.width = `${Math.min(100, Math.max(0, tel.ram_pct ?? 0))}%`;

    const vramTot = tel.vram_total_gb || 0;
    const vramPct = vramTot > 0 ? ((tel.vram_usada_gb || 0) / vramTot) * 100 : 0;
    $("tel-vram-val").textContent = vramTot > 0
      ? `${(tel.vram_usada_gb ?? 0).toFixed(1)} / ${vramTot.toFixed(1)} GB`
      : "CPU Pura";
    $("bar-vram").style.width = `${Math.min(100, Math.max(0, vramPct))}%`;

    $("tel-disk-val").textContent = `${(tel.disco_libre_gb ?? 0).toFixed(1)} GB libres`;
    $("bar-disk").style.width = `${Math.min(100, Math.max(0, tel.disco_pct ?? 0))}%`;

    $("inspector-temp-badge").textContent = tel.temperatura_c != null ? `${tel.temperatura_c.toFixed(1)} °C` : "N/D";
    $("hw-gpu-name").textContent = `${hw.nombre_gpu_principal || "CPU"} (${hw.tipo_gpu_principal || "CPU"})`;
    $("hw-hash").textContent = `SHA: ${(hw.hash_hardware || "").slice(0, 16)}...`;

    const pairSel = $("pair-select");
    const prevVal = pairSel.value;
    const parejas = status.parejas_recomendadas || [];
    pairSel.innerHTML = parejas
      .map((p) => {
        const tag = p.descargado_gen ? "[Disco]" : "[Catálogo]";
        const vel = p.tok_s ? `${Number(p.tok_s).toFixed(1)} t/s` : "";
        return `<option value="${esc(p.modelo_gen_id)}" data-emb="${esc(p.modelo_emb_id || "bge-m3-q4")}">${esc(p.modelo_gen_id)} + ${esc(p.modelo_emb_id)} · ${vel} ${tag}</option>`;
      })
      .join("");
    if (prevVal && [...pairSel.options].some((o) => o.value === prevVal)) {
      pairSel.value = prevVal;
    } else if (srv.modelo_activo_id && [...pairSel.options].some((o) => o.value === srv.modelo_activo_id)) {
      pairSel.value = srv.modelo_activo_id;
    }

    const activeModel = srv.modelo_activo_id || pairSel.value || tier.chat || "Auto";
    $("composer-model-tag").textContent = `Modelo: ${activeModel}`;

    $("hero-tier-badges").innerHTML = [
      `<span class="badge badge-indigo">Tier: ${esc((tier.tier || "local").toUpperCase())}</span>`,
      `<span class="badge badge-cyan">${esc(hw.nombre_gpu_principal || "CPU")}</span>`,
      `<span class="badge badge-emerald">${(hw.ram_total_gb ?? 0).toFixed(1)} GB RAM</span>`,
    ].join("");

    $("tier-summary-card").innerHTML = `
      <div><strong>${esc((tier.tier || "").toUpperCase())}</strong></div>
      <div class="muted-text">${esc(tier.descripcion || "")}</div>
    `;

    $("sidebar-pairs-list").innerHTML = parejas
      .map(
        (p, idx) => `
        <div class="list-card" data-pair-gen="${esc(p.modelo_gen_id)}" data-pair-emb="${esc(p.modelo_emb_id)}">
          <div class="list-card-top">
            <span>${idx === 0 ? "★ " : ""}${esc(p.modelo_gen_id)}</span>
            <span class="badge ${p.descargado_gen ? "badge-emerald" : "badge-muted"}">${p.descargado_gen ? "Disco" : "Catálogo"}</span>
          </div>
          <div class="list-card-sub">AST: ${esc(p.modelo_emb_id)} · ${Number(p.tok_s || 0).toFixed(1)} t/s · ${esc(p.clasificacion_rendimiento || "")}</div>
        </div>
      `
      )
      .join("");

    $("sidebar-pairs-list").querySelectorAll("[data-pair-gen]").forEach((el) => {
      el.addEventListener("click", () => {
        pairSel.value = el.getAttribute("data-pair-gen");
        startSelectedEngine();
      });
    });
  }

  async function refreshStatus() {
    try {
      const data = await api("/api/status");
      updateStatusUI(data);
    } catch (err) {
      console.error(err);
    }
  }

  async function loadProjects() {
    const data = await api("/api/projects");
    state.projects = data.proyectos || [];
    const list = $("projects-list");
    if (!state.projects.length) {
      list.innerHTML = `<div class="muted-text">No hay proyectos registrados. Pulsa + para añadir una carpeta.</div>`;
    } else {
      list.innerHTML = state.projects
        .map(
          (p) => `
          <div class="list-card ${p.id === state.activeProjectId ? "active" : ""}" data-project-id="${esc(p.id)}">
            <div class="list-card-top">
              <span>${esc(p.nombre)}</span>
              <span class="badge badge-cyan">${p.documentos_count || 0} docs</span>
            </div>
            <div class="list-card-sub">${esc(p.ruta_directorio)}</div>
          </div>
        `
        )
        .join("");
      list.querySelectorAll("[data-project-id]").forEach((el) => {
        el.addEventListener("click", () => selectProject(el.getAttribute("data-project-id")));
      });
    }

    if (!state.activeProjectId && state.projects.length) {
      await selectProject(state.projects[0].id);
    } else if (state.activeProjectId) {
      await loadProjectFilesAndAst(state.activeProjectId);
    }
  }

  async function selectProject(projectId) {
    state.activeProjectId = projectId;
    const proj = state.projects.find((p) => p.id === projectId);
    $("active-context-badge").textContent = proj ? `Proyecto: ${proj.nombre}` : "Sin proyecto activo";
    $("composer-project-tag").textContent = proj ? `RAG: ${proj.nombre}` : "RAG: Inactivo";
    $("projects-list").querySelectorAll("[data-project-id]").forEach((el) => {
      el.classList.toggle("active", el.getAttribute("data-project-id") === projectId);
    });
    await Promise.all([
      loadProjectFilesAndAst(projectId),
      loadSessions(),
      loadMemory(),
    ]);
  }

  async function loadProjectFilesAndAst(projectId, semilla = "") {
    if (!projectId) {
      $("project-files-list").innerHTML = `<div class="muted-text">Selecciona un proyecto para ver archivos.</div>`;
      return;
    }
    const qs = new URLSearchParams({ proyecto_id: projectId });
    if (semilla) qs.set("semilla", semilla);
    const data = await api(`/api/projects/files?${qs.toString()}`);
    const docs = data.documentos || [];
    $("project-files-list").innerHTML = docs.length
      ? docs
          .map(
            (d) => `
            <div class="file-row" title="${esc(d.ruta_relativa)}">
              <span class="file-name">${esc(d.ruta_relativa)}</span>
              <span class="badge">${esc(d.tipo_documento)} · ${d.nodos_ast_count}</span>
            </div>
          `
          )
          .join("")
      : `<div class="muted-text">Sin documentos indexados aún.</div>`;

    state.astData = data;
    renderAstView();
  }

  function renderAstView() {
    const nodos = state.astData.nodos_ast || [];
    const rels = state.astData.relaciones_ast || [];
    const exp = state.astData.expansion || [];

    $("ast-nodes-count").textContent = String(nodos.length);
    $("ast-edges-count").textContent = String(exp.length || rels.length);

    $("ast-nodes-container").innerHTML = nodos.length
      ? nodos
          .map(
            (n) => `
            <div class="list-card" data-ast-seed="${esc(n.id_nodo)}">
              <div class="list-card-top">
                <span>${esc(n.nombre)}</span>
                <span class="badge badge-indigo">${esc(n.tipo)}</span>
              </div>
              <div class="list-card-sub">${esc(n.ruta_archivo)}:${n.linea_inicio}-${n.linea_fin} · ${esc(n.id_nodo)}</div>
            </div>
          `
          )
          .join("")
      : `<div class="muted-text">No hay nodos AST indexados para este proyecto.</div>`;

    $("ast-nodes-container").querySelectorAll("[data-ast-seed]").forEach((el) => {
      el.addEventListener("click", () => {
        const seed = el.getAttribute("data-ast-seed");
        $("ast-seed-input").value = seed;
        if (state.activeProjectId) {
          loadProjectFilesAndAst(state.activeProjectId, seed);
        }
      });
    });

    if (exp.length) {
      $("ast-expansion-container").innerHTML = exp
        .map(
          (e) => `
          <div class="list-card">
            <div class="list-card-top">
              <span>${esc(e.nombre)}</span>
              <span class="badge badge-cyan">Salto ${e.profundidad} · ${esc(e.relaciones || "")}</span>
            </div>
            <div class="list-card-sub">${esc(e.ruta_archivo)}:${e.linea_inicio}-${e.linea_fin}</div>
          </div>
        `
        )
        .join("");
    } else if (rels.length) {
      $("ast-expansion-container").innerHTML = rels
        .map(
          (r) => `
          <div class="file-row">
            <span class="file-name">${esc(r.origen_id)} &rarr; ${esc(r.destino_id)}</span>
            <span class="badge badge-indigo">${esc(r.tipo_relacion)}</span>
          </div>
        `
        )
        .join("");
    } else {
      $("ast-expansion-container").innerHTML = `<div class="muted-text">Pulsa en un nodo AST o introduce una semilla para expandir dependencias multihop.</div>`;
    }
  }

  async function loadSessions() {
    const qs = state.activeProjectId ? `?proyecto_id=${encodeURIComponent(state.activeProjectId)}` : "";
    const data = await api(`/api/sessions${qs}`);
    state.sessions = data.sesiones || [];
    const cont = $("sessions-list");
    cont.innerHTML = state.sessions.length
      ? state.sessions
          .map(
            (s) => `
            <div class="list-card ${s.id === state.activeSessionId ? "active" : ""}" data-session-id="${esc(s.id)}">
              <div class="list-card-top">
                <span>${esc(s.titulo)}</span>
                <button class="icon-btn btn-del-session" data-del-session="${esc(s.id)}" title="Eliminar sesión" type="button">×</button>
              </div>
              <div class="list-card-sub">${esc(s.modelo_id)} · ${esc((s.fecha_actualizacion || "").slice(0, 16))}</div>
            </div>
          `
          )
          .join("")
      : `<div class="muted-text">Sin sesiones guardadas todavía.</div>`;

    cont.querySelectorAll("[data-session-id]").forEach((el) => {
      el.addEventListener("click", (ev) => {
        if (ev.target.closest("[data-del-session]")) return;
        openSession(el.getAttribute("data-session-id"));
      });
    });

    cont.querySelectorAll("[data-del-session]").forEach((btn) => {
      btn.addEventListener("click", async (ev) => {
        ev.stopPropagation();
        const sid = btn.getAttribute("data-del-session");
        await api(`/api/sessions?sesion_id=${encodeURIComponent(sid)}`, { method: "DELETE" });
        if (state.activeSessionId === sid) {
          state.activeSessionId = null;
          renderChatHistory([]);
        }
        await loadSessions();
        showToast("Sesión eliminada", "info");
      });
    });
  }

  async function openSession(sesionId) {
    state.activeSessionId = sesionId;
    $("active-session-pill").textContent = `Sesión: ${sesionId}`;
    const data = await api(`/api/sessions/messages?sesion_id=${encodeURIComponent(sesionId)}`);
    renderChatHistory(data.mensajes || []);
    await loadSessions();
    await loadMemory();
  }

  function renderChatHistory(mensajes) {
    const cont = $("chat-messages");
    cont.innerHTML = "";
    $("chat-hero").classList.toggle("hidden", mensajes.length > 0);
    for (const m of mensajes) {
      appendChatMessage(m.rol, m.contenido, m.fuentes || [], null);
    }
    scrollChatBottom();
  }

  function appendChatMessage(role, content, fuentes = [], metricas = null) {
    $("chat-hero").classList.add("hidden");
    const cont = $("chat-messages");
    const card = document.createElement("article");
    card.className = `msg-card ${role === "user" ? "msg-user" : "msg-assistant"}`;

    const label = role === "user" ? "USUARIO" : "ASISTENTE GUARIDA";
    let fuentesHtml = "";
    if (Array.isArray(fuentes) && fuentes.length) {
      const items = fuentes
        .map((f) => {
          const nom = f.nombre || f.seccion || "";
          const score = f.relevancia != null ? Number(f.relevancia).toFixed(2) : "--";
          return `
            <div class="source-item">
              <span>${esc(f.archivo || "")}:${esc(f.lineas || "")} ${nom ? "(" + esc(nom) + ")" : ""}</span>
              <span class="badge badge-cyan">Score ${score}</span>
            </div>
          `;
        })
        .join("");
      fuentesHtml = `
        <details class="sources-details">
          <summary>Fuentes citadas RAG (${fuentes.length})</summary>
          ${items}
        </details>
      `;
    }

    let metricsHtml = "";
    if (metricas) {
      const items = [
        `<span>Prompt: <strong>${metricas.tokens_enviados_realmente ?? 0}</strong> tok</span>`,
        `<span>Salida: <strong>${metricas.tokens_generados ?? 0}</strong> tok</span>`,
        `<span>TG: <strong>${Number(metricas.velocidad_generacion_tok_s ?? 0).toFixed(2)} tok/s</strong></span>`,
        `<span>Latencia: <strong>${Number(metricas.tiempo_total_s ?? 0).toFixed(2)}s</strong></span>`,
      ];
      if (metricas.rag) {
        items.push(`<span>RAG: <strong>${Number(metricas.rag.tiempo_busqueda_ms ?? 0).toFixed(1)} ms</strong></span>`);
      }
      metricsHtml = `<div class="msg-metrics-bar">${items.join("")}</div>`;
    }

    card.innerHTML = `
      <div class="msg-header">
        <span>${label}</span>
      </div>
      <div class="msg-body">${renderMarkdown(content)}</div>
      ${fuentesHtml}
      ${metricsHtml}
    `;

    card.querySelectorAll(".btn-copy-code").forEach((btn) => {
      btn.addEventListener("click", () => {
        const pre = btn.closest(".code-block-wrap").querySelector("code");
        navigator.clipboard?.writeText(pre.textContent || "");
        btn.textContent = "Copiado";
        setTimeout(() => { btn.textContent = "Copiar"; }, 1400);
      });
    });

    cont.appendChild(card);
    scrollChatBottom();
    return card;
  }

  function updateRagInspector(rag) {
    if (!rag) return;
    $("rag-speed-badge").textContent = `${Number(rag.tiempo_busqueda_ms ?? 0).toFixed(1)} ms`;
    $("rag-speed-badge").className = "badge badge-cyan";
    $("rag-eval").textContent = String(rag.fragmentos_evaluados ?? 0);
    $("rag-cited").textContent = String(rag.fragmentos_citados ?? 0);
    $("rag-score").textContent = rag.top_score != null ? Number(rag.top_score).toFixed(2) : "--";
    $("rag-tokens").textContent = String(rag.tokens_contexto ?? 0);
    const files = rag.ficheros_consultados || [];
    $("rag-files-chips").innerHTML = files
      .map((f) => `<span class="badge">${esc(f)}</span>`)
      .join("");
  }

  function scrollChatBottom() {
    const sc = $("chat-scroll");
    sc.scrollTop = sc.scrollHeight;
  }

  async function loadMemory() {
    const inc = $("chk-show-superseded").checked;
    const qs = new URLSearchParams();
    if (state.activeProjectId) qs.set("proyecto_id", state.activeProjectId);
    if (state.activeSessionId) qs.set("sesion_id", state.activeSessionId);
    if (inc) qs.set("incluir_superseded", "1");

    const data = await api(`/api/memory?${qs.toString()}`);
    state.memory = data.hechos || [];
    const activos = state.memory.filter((h) => h.estado !== "superseded");
    $("mem-count-badge").textContent = String(activos.length);

    $("sidebar-memory-list").innerHTML = state.memory.length
      ? state.memory
          .map((h) => {
            const sup = h.estado === "superseded";
            return `
              <div class="list-card">
                <div class="list-card-top">
                  <span>#${h.id} ${esc(h.sujeto)}</span>
                  <span class="badge ${sup ? "badge-amber" : "badge-emerald"}">${sup ? "SUPERSEDED" : "ACTIVO"}</span>
                </div>
                <div class="list-card-sub">${esc(h.predicado)} &rarr; ${esc(h.objeto)}</div>
              </div>
            `;
          })
          .join("")
      : `<div class="muted-text">Sin hechos registrados.</div>`;

    $("inspector-memory-list").innerHTML = activos.length
      ? activos
          .map(
            (h) => `<div class="mem-pill">${esc(h.sujeto)} | ${esc(h.predicado)} | ${esc(h.objeto)}</div>`
          )
          .join("")
      : `<div class="muted-text">Ningún hecho activo en contexto.</div>`;
  }

  async function loadCatalog() {
    const data = await api("/api/models");
    state.models = data.modelos || [];
    renderCatalogTable();
  }

  function renderCatalogTable() {
    const f = state.catalogFilter;
    const filtrados = state.models.filter((m) => {
      if (f === "all") return true;
      if (f === "local") return m.en_disco;
      return m.categoria === f;
    });

    $("catalog-tbody").innerHTML = filtrados
      .map((m) => {
        const velPrefix = m.es_medido_real ? "" : "~";
        const afin = m.afinamiento
          ? `ngl=${m.afinamiento.n_gpu_layers}, c=${m.afinamiento.ctx_size}, ${m.afinamiento.kv_cache_tipo}`
          : "Sin afinar";
        const estadoBadge = m.en_disco
          ? `<span class="badge badge-emerald">En disco (${m.tamano_mb || "?"} MB)</span>`
          : `<span class="badge badge-muted">Catálogo</span>`;
        const dlBtn = m.en_disco
          ? ""
          : `<button class="btn btn-outline btn-xs btn-dl-model" data-model="${esc(m.id)}" type="button">Descargar</button>`;
        return `
          <tr>
            <td>
              <strong>${esc(m.id)}</strong>
              <div class="muted-text">${esc(m.nombre_legible)}</div>
            </td>
            <td><span class="badge">${esc((m.formato || "gguf").toUpperCase())}</span></td>
            <td>${Number(m.tamano_gb).toFixed(2)} GB</td>
            <td>${velPrefix}${Number(m.tok_s_estimado).toFixed(1)} t/s<div class="muted-text">${esc(m.clasificacion_chat)}</div></td>
            <td><span class="badge badge-cyan">${esc(m.estrategia_vram)}</span></td>
            <td><code>${esc(afin)}</code></td>
            <td>${estadoBadge}</td>
            <td>
              <div class="panel-actions">
                <button class="btn btn-ghost btn-xs btn-tune-model" data-model="${esc(m.id)}" type="button">Afinar</button>
                ${dlBtn}
                <button class="btn btn-primary btn-xs btn-load-model" data-model="${esc(m.id)}" type="button">Cargar</button>
              </div>
            </td>
          </tr>
        `;
      })
      .join("");

    $("catalog-tbody").querySelectorAll(".btn-tune-model").forEach((btn) => {
      btn.addEventListener("click", async () => {
        const mid = btn.getAttribute("data-model");
        btn.disabled = true;
        try {
          await api("/api/models/tune", { method: "POST", body: JSON.stringify({ modelo_id: mid }) });
          showToast(`Modelo '${mid}' afinado en SQLite`, "ok");
          await loadCatalog();
        } catch (err) {
          showToast(err.message, "err");
        } finally {
          btn.disabled = false;
        }
      });
    });

    $("catalog-tbody").querySelectorAll(".btn-dl-model").forEach((btn) => {
      btn.addEventListener("click", async () => {
        const mid = btn.getAttribute("data-model");
        btn.disabled = true;
        showToast(`Descargando '${mid}'...`, "info");
        try {
          await api("/api/models/download", { method: "POST", body: JSON.stringify({ modelo_id: mid }) });
          showToast(`Modelo '${mid}' listo en disco`, "ok");
          await Promise.all([loadCatalog(), refreshStatus()]);
        } catch (err) {
          showToast(err.message, "err");
        } finally {
          btn.disabled = false;
        }
      });
    });

    $("catalog-tbody").querySelectorAll(".btn-load-model").forEach((btn) => {
      btn.addEventListener("click", async () => {
        const mid = btn.getAttribute("data-model");
        await startEngine(mid);
      });
    });
  }

  async function startEngine(modeloId, motorEmbId = null) {
    if (!modeloId) return;
    $("btn-start-engine").disabled = true;
    showToast(`Iniciando motor para '${modeloId}'...`, "info");
    try {
      await api("/api/server/start", {
        method: "POST",
        body: JSON.stringify({ modelo_id: modeloId, motor_emb_id: motorEmbId }),
      });
      showToast(`Motor activo con '${modeloId}'`, "ok");
      await Promise.all([refreshStatus(), loadCatalog()]);
    } catch (err) {
      showToast(err.message, "err");
    } finally {
      $("btn-start-engine").disabled = false;
    }
  }

  function startSelectedEngine() {
    const sel = $("pair-select");
    const opt = sel.selectedOptions[0];
    const emb = opt ? opt.getAttribute("data-emb") : null;
    startEngine(sel.value, emb);
  }

  async function sendChatMessage(text) {
    if (state.sending) return;
    const msg = text.trim();
    if (!msg) return;

    state.sending = true;
    $("btn-send-chat").disabled = true;
    $("btn-send-chat").textContent = "Pensando...";
    appendChatMessage("user", msg, [], null);

    const sel = $("pair-select");
    const opt = sel.selectedOptions[0];
    const embId = opt ? opt.getAttribute("data-emb") : null;

    try {
      const res = await api("/api/chat", {
        method: "POST",
        body: JSON.stringify({
          mensaje: msg,
          sesion_id: state.activeSessionId,
          proyecto_id: state.activeProjectId,
          modelo_id: sel.value || null,
          motor_emb_id: embId,
        }),
      });

      if (res.sesion_id && res.sesion_id !== state.activeSessionId) {
        state.activeSessionId = res.sesion_id;
        $("active-session-pill").textContent = `Sesión: ${res.sesion_id}`;
      }

      appendChatMessage("assistant", res.respuesta || "", res.fuentes || [], res.metricas || null);
      if (res.metricas && res.metricas.rag) {
        updateRagInspector(res.metricas.rag);
      }
      if (res.hechos_detectados && res.hechos_detectados.length) {
        showToast(`${res.hechos_detectados.length} hecho(s) guardado(s) en memoria`, "ok");
      }
      if (res.redacciones_privacidad > 0) {
        showToast(`Privacidad: ${res.redacciones_privacidad} dato(s) sanitizado(s)`, "info");
      }

      await Promise.all([loadSessions(), loadMemory(), refreshStatus()]);
    } catch (err) {
      appendChatMessage("assistant", `**[Error de inferencia]:** ${err.message}`, [], null);
      showToast(err.message, "err");
    } finally {
      state.sending = false;
      $("btn-send-chat").disabled = false;
      $("btn-send-chat").textContent = "Enviar";
    }
  }

  function wireNavigation() {
    document.querySelectorAll(".rail-btn[data-rail]").forEach((btn) => {
      btn.addEventListener("click", () => {
        const target = btn.getAttribute("data-rail");
        document.querySelectorAll(".rail-btn[data-rail]").forEach((b) => b.classList.remove("active"));
        btn.classList.add("active");
        document.querySelectorAll(".sidebar-view").forEach((v) => v.classList.remove("active"));
        $(`sidebar-${target}`).classList.add("active");
        if (target === "models") {
          switchWorkspaceTab("catalog");
        }
      });
    });

    document.querySelectorAll(".tab-btn[data-tab]").forEach((btn) => {
      btn.addEventListener("click", () => switchWorkspaceTab(btn.getAttribute("data-tab")));
    });

    $("btn-toggle-inspector").addEventListener("click", () => {
      $("inspector-panel").classList.toggle("hidden");
      $("btn-toggle-inspector").classList.toggle("active");
    });

    $("btn-open-models-tab").addEventListener("click", () => switchWorkspaceTab("catalog"));
  }

  function switchWorkspaceTab(tab) {
    document.querySelectorAll(".tab-btn[data-tab]").forEach((b) => {
      const isAct = b.getAttribute("data-tab") === tab;
      b.classList.toggle("active", isAct);
      b.setAttribute("aria-selected", String(isAct));
    });
    document.querySelectorAll(".workspace-view").forEach((v) => v.classList.remove("active"));
    $(`view-${tab}`).classList.add("active");
    if (tab === "catalog") loadCatalog();
    if (tab === "ast" && state.activeProjectId) loadProjectFilesAndAst(state.activeProjectId);
  }

  function wireActions() {
    $("btn-start-engine").addEventListener("click", startSelectedEngine);
    $("btn-stop-engine").addEventListener("click", async () => {
      try {
        await api("/api/server/stop", { method: "POST", body: "{}" });
        showToast("Servidor llama-server detenido", "info");
        await refreshStatus();
      } catch (err) {
        showToast(err.message, "err");
      }
    });

    $("btn-privacy-toggle").addEventListener("click", async () => {
      const current = $("privacy-mode-label").textContent.trim();
      const nextMode = current === "rgpd_estricto" ? "estandar" : "rgpd_estricto";
      try {
        await api("/api/privacy", { method: "POST", body: JSON.stringify({ modo: nextMode }) });
        showToast(`Privacidad cambiada a '${nextMode}'`, "ok");
        await refreshStatus();
      } catch (err) {
        showToast(err.message, "err");
      }
    });

    $("btn-toggle-new-project").addEventListener("click", () => {
      $("form-new-project").classList.toggle("hidden");
    });
    $("btn-cancel-new-project").addEventListener("click", () => {
      $("form-new-project").classList.add("hidden");
    });
    $("btn-refresh-projects").addEventListener("click", loadProjects);

    $("form-new-project").addEventListener("submit", async (ev) => {
      ev.preventDefault();
      try {
        const res = await api("/api/projects", {
          method: "POST",
          body: JSON.stringify({
            nombre: $("proj-name").value,
            ruta_directorio: $("proj-path").value,
            descripcion: $("proj-desc").value,
          }),
        });
        $("form-new-project").reset();
        $("form-new-project").classList.add("hidden");
        showToast(`Proyecto '${res.proyecto.nombre}' indexado`, "ok");
        await loadProjects();
        await selectProject(res.proyecto.id);
      } catch (err) {
        showToast(err.message, "err");
      }
    });

    $("btn-reindex-active").addEventListener("click", async () => {
      if (!state.activeProjectId) return;
      showToast("Reindexando proyecto...", "info");
      try {
        const res = await api("/api/projects/index", {
          method: "POST",
          body: JSON.stringify({ proyecto_id: state.activeProjectId }),
        });
        const r = res.resumen || {};
        showToast(`Indexados ${r.archivos_procesados ?? 0} archivos, ${r.nodos_ast ?? 0} nodos AST`, "ok");
        await loadProjects();
      } catch (err) {
        showToast(err.message, "err");
      }
    });

    $("btn-new-session").addEventListener("click", async () => {
      try {
        const res = await api("/api/sessions", {
          method: "POST",
          body: JSON.stringify({
            proyecto_id: state.activeProjectId,
            modelo_id: $("pair-select").value || null,
          }),
        });
        await openSession(res.sesion.id);
        switchWorkspaceTab("chat");
      } catch (err) {
        showToast(err.message, "err");
      }
    });

    $("chk-show-superseded").addEventListener("change", loadMemory);
    $("form-new-fact").addEventListener("submit", async (ev) => {
      ev.preventDefault();
      try {
        await api("/api/memory", {
          method: "POST",
          body: JSON.stringify({
            sujeto: $("fact-subject").value,
            predicado: $("fact-predicate").value,
            objeto: $("fact-object").value,
            proyecto_id: state.activeProjectId,
            sesion_id: state.activeSessionId,
          }),
        });
        $("form-new-fact").reset();
        showToast("Hecho guardado en memoria declarativa", "ok");
        await loadMemory();
      } catch (err) {
        showToast(err.message, "err");
      }
    });

    $("btn-expand-ast").addEventListener("click", () => {
      if (state.activeProjectId) {
        loadProjectFilesAndAst(state.activeProjectId, $("ast-seed-input").value.trim());
      }
    });

    const tuneAll = async () => {
      showToast("Auto-afinando modelos locales...", "info");
      try {
        const res = await api("/api/models/tune", { method: "POST", body: "{}" });
        showToast(`${(res.afinados || []).length} modelo(s) afinado(s)`, "ok");
        await Promise.all([loadCatalog(), refreshStatus()]);
      } catch (err) {
        showToast(err.message, "err");
      }
    };
    $("btn-tune-all-side").addEventListener("click", tuneAll);
    $("btn-tune-all-main").addEventListener("click", tuneAll);

    $("catalog-filters").querySelectorAll(".filter-btn").forEach((btn) => {
      btn.addEventListener("click", () => {
        $("catalog-filters").querySelectorAll(".filter-btn").forEach((b) => b.classList.remove("active"));
        btn.classList.add("active");
        state.catalogFilter = btn.getAttribute("data-filter");
        renderCatalogTable();
      });
    });

    document.querySelectorAll(".chip-btn[data-prompt]").forEach((btn) => {
      btn.addEventListener("click", () => {
        sendChatMessage(btn.getAttribute("data-prompt"));
      });
    });

    document.querySelectorAll(".cmd-chip[data-insert]").forEach((btn) => {
      btn.addEventListener("click", () => {
        const txt = btn.getAttribute("data-insert");
        const input = $("chat-input");
        input.value = txt;
        input.focus();
      });
    });

    $("chat-form").addEventListener("submit", (ev) => {
      ev.preventDefault();
      const input = $("chat-input");
      const val = input.value;
      if (!val.trim()) return;
      input.value = "";
      sendChatMessage(val);
    });

    $("chat-input").addEventListener("keydown", (ev) => {
      if (ev.key === "Enter" && !ev.shiftKey) {
        ev.preventDefault();
        $("chat-form").requestSubmit();
      }
    });
  }

  let cierreManualEnviado = false;

  function enviarBeaconCierre(motivo = "tab_closed") {
    if (cierreManualEnviado) return;
    const payload = JSON.stringify({ motivo });
    if (navigator.sendBeacon) {
      const blob = new Blob([payload], { type: "application/json" });
      navigator.sendBeacon("/api/web/close", blob);
    } else {
      fetch("/api/web/close", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: payload,
        keepalive: true,
      }).catch(() => {});
    }
  }

  async function cerrarAplicacionWeb() {
    cierreManualEnviado = true;
    try {
      await api("/api/web/close", {
        method: "POST",
        body: JSON.stringify({ motivo: "manual" }),
      });
    } catch (_) {
      // Ignorar si el servidor ya inició apagado
    }
    document.body.innerHTML = `
      <div style="display:grid;place-items:center;height:100vh;background:#090b10;color:#eef2ff;font-family:system-ui,sans-serif;text-align:center;padding:24px;">
        <div>
          <h2 style="margin:0 0 8px;">GuarIdA Web cerrada correctamente</h2>
          <p style="color:#9aa5be;margin:0;">El servidor local y el motor de inferencia se han detenido. Puedes cerrar esta pestaña.</p>
        </div>
      </div>
    `;
    window.close();
  }

  async function refreshTunnelStatus() {
    const btn = $("btn-tunnel-toggle");
    const lbl = $("tunnel-status-label");
    if (!btn || !lbl) return;
    try {
      const st = await api("/api/tunnel/status");
      if (st.activo) {
        lbl.textContent = "ON";
        btn.title = `Activo: ${st.url_publica} (Código: ${st.token_acceso})`;
      } else {
        lbl.textContent = "OFF";
        btn.title = "Abrir túnel HTTPS gratuito (cloudflared)";
      }
    } catch (_) {
      lbl.textContent = "OFF";
    }
  }

  async function toggleTunnelRemoto() {
    const btn = $("btn-tunnel-toggle");
    const lbl = $("tunnel-status-label");
    if (!btn || !lbl) return;
    btn.disabled = true;
    try {
      const actual = await api("/api/tunnel/status");
      if (actual.activo) {
        await api("/api/tunnel/stop", { method: "POST", body: JSON.stringify({}) });
        await refreshTunnelStatus();
      } else {
        lbl.textContent = "...";
        const res = await api("/api/tunnel/start", { method: "POST", body: JSON.stringify({}) });
        await refreshTunnelStatus();
        if (res.url_con_token) {
          navigator.clipboard?.writeText(res.url_con_token).catch(() => {});
          window.prompt(
            `Túnel HTTPS activo (copiado al portapapeles).\nCódigo: ${res.token_acceso}`,
            res.url_con_token
          );
        }
      }
    } catch (err) {
      window.alert(`No se pudo cambiar el túnel remoto: ${err.message || err}`);
      await refreshTunnelStatus();
    } finally {
      btn.disabled = false;
    }
  }

  async function init() {
    wireNavigation();
    wireActions();
    $("btn-tunnel-toggle")?.addEventListener("click", toggleTunnelRemoto);
    $("btn-close-web")?.addEventListener("click", cerrarAplicacionWeb);
    window.addEventListener("pagehide", () => enviarBeaconCierre("tab_closed"));
    window.addEventListener("beforeunload", () => enviarBeaconCierre("tab_closed"));
    await Promise.all([refreshStatus(), refreshTunnelStatus(), loadProjects(), loadSessions(), loadMemory(), loadCatalog()]);
    setInterval(refreshStatus, 3000);
  }

  init();
})();
