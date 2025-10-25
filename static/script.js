async function sendSancion(e) {
  e.preventDefault();
  
  const form = document.getElementById("sancionForm");
  const msgDiv = document.getElementById("msg");
  const button = document.getElementById("submit-button");

  // --- MEJORA PROFESIONAL: Desactivar botón ---
  button.disabled = true;
  button.innerText = "Enviando...";
  msgDiv.className = "msg-loading";
  msgDiv.innerText = "Enviando...";

  // Recoge todos los datos, INCLUYENDO EL NUEVO USER_ID
  const payload = {
    fecha: document.getElementById("fecha").value || null,
    objetivo: document.getElementById("objetivo").value,
    user_id: document.getElementById("user_id").value, // <-- ¡¡CAMPO NUEVO!!
    accion: document.getElementById("accion").value,
    motivo: document.getElementById("motivo").value,
    gravedad: document.getElementById("gravedad").value,
    conteo: document.getElementById("conteo").value,
    pruebas: document.getElementById("pruebas").value
  };

  try {
    const res = await fetch("/send_sancion", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload)
    });
    const data = await res.json();
    
    if (data.ok) {
      msgDiv.className = "msg-success";
      msgDiv.innerText = "✅ Sanción enviada y guardada";
      form.reset(); // <-- MEJORA PROFESIONAL: Limpia todo el formulario
      loadHistorial();
    } else {
      msgDiv.className = "msg-error";
      msgDiv.innerText = "❌ Error: " + (data.msg || "desconocido");
    }
  } catch (err) {
    msgDiv.className = "msg-error";
    msgDiv.innerText = "❌ Error de red: "S" + err.message;
  }

  // --- MEJORA PROFESIONAL: Reactivar botón ---
  button.disabled = false;
  button.innerText = "Enviar sanción";
  
  // Oculta el mensaje después de 5 segundos
  setTimeout(() => {
    msgDiv.innerText = "";
    msgDiv.className = "";
  }, 5000);
  
  return false;
}

async function loadHistorial() {
  const hist = document.getElementById("historial");
  hist.innerText = "Cargando...";
  try {
    const res = await fetch("/api/sanciones");
    const d = await res.json();
    if (!d.ok) {
      hist.innerText = "Error: No autorizado";
      return;
    }
    const rows = d.data.slice(0, 20); // Muestra solo los últimos 20
    
    if (rows.length === 0) {
      hist.innerText = "No hay registros todavía.";
      return;
    }
    
    // Mapea los datos a HTML
    hist.innerHTML = rows.map(r => {
      // Formatea la fecha para que sea más legible
      const fecha = new Date(r.fecha || r.created_at).toLocaleString('es-ES', {
          day: '2-digit', month: '2-digit', year: 'numeric',
          hour: '2-digit', minute: '2-digit'
      });
      
      return `<div class="entry">
        <strong>${r.accion.toUpperCase()}</strong> — ${r.objetivo} <br/>
        <small>${r.moderador} • ${fecha}</small>
        <div class="motivo">${r.motivo}</div>
      </div>`;
    }).join("");
    
  } catch (e) {
    hist.innerText = "Error cargando historial: " + e.message;
  }
}

// Carga el historial en cuanto la página esté lista
window.addEventListener("load", loadHistorial);