async function sendSancion(e){
  e.preventDefault();
  const payload = {
    fecha: document.getElementById("fecha").value || null,
    objetivo: document.getElementById("objetivo").value,
    accion: document.getElementById("accion").value,
    motivo: document.getElementById("motivo").value,
    gravedad: document.getElementById("gravedad").value,
    conteo: document.getElementById("conteo").value,
    pruebas: document.getElementById("pruebas").value
  };
  const msgDiv = document.getElementById("msg");
  msgDiv.innerText = "Enviando...";
  try{
    const res = await fetch("/send_sancion", {
      method: "POST",
      headers: {"Content-Type": "application/json"},
      body: JSON.stringify(payload)
    });
    const data = await res.json();
    if(data.ok){
      msgDiv.innerText = "✅ Sanción enviada y guardada";
      loadHistorial();
      // limpiar form parcialmente
      document.getElementById("motivo").value = "";
      document.getElementById("pruebas").value = "";
    } else {
      msgDiv.innerText = "Error: " + (data.msg || "unknown");
    }
  } catch(err){
    msgDiv.innerText = "Error de red: " + err;
  }
  setTimeout(()=> msgDiv.innerText = "", 5000);
  return false;
}

async function loadHistorial(){
  const hist = document.getElementById("historial");
  hist.innerText = "Cargando...";
  try{
    const res = await fetch("/api/sanciones");
    const d = await res.json();
    if(!d.ok){ hist.innerText = "No autorizado"; return;}
    const rows = d.data.slice(0,20);
    hist.innerHTML = rows.map(r => {
      return `<div class="entry">
        <strong>${r.accion.toUpperCase()}</strong> — ${r.objetivo} <br/>
        <small>${r.moderador} • ${r.fecha || r.created_at}</small>
        <div>${r.motivo}</div>
      </div>`;
    }).join("");
    if(rows.length===0) hist.innerText = "No hay registros";
  } catch(e){
    hist.innerText = "Error cargando historial";
  }
}

window.addEventListener("load", loadHistorial);
