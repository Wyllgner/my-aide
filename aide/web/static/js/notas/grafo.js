// ---------- grafo: arrastar, zoom e vizinhas ----------
document.querySelectorAll("svg.grafo").forEach(function (svg) {
  var vb = svg.viewBox.baseVal;
  var original = { x: vb.x, y: vb.y, w: vb.width, h: vb.height };
  var arrasto = null;
  var moveu = false;

  function paraSvg(evento) {
    var caixa = svg.getBoundingClientRect();
    return { x: vb.x + (evento.clientX - caixa.left) / caixa.width * vb.width,
             y: vb.y + (evento.clientY - caixa.top) / caixa.height * vb.height };
  }

  // o grafo local fica no meio da página: a roda sozinha rola a página,
  // e o zoom pede Ctrl — senão quem rola passando por cima fica preso nele
  var local = svg.classList.contains("local");
  svg.addEventListener("wheel", function (e) {
    if (local && !e.ctrlKey && !e.metaKey) { return; }
    e.preventDefault();
    var ponto = paraSvg(e);
    var fator = e.deltaY < 0 ? 0.85 : 1 / 0.85;
    var largura = Math.min(Math.max(vb.width * fator, original.w / 8), original.w * 3);
    var escala = largura / vb.width;
    vb.x = ponto.x - (ponto.x - vb.x) * escala;
    vb.y = ponto.y - (ponto.y - vb.y) * escala;
    vb.width = largura;
    vb.height = vb.height * escala;
  }, { passive: false });

  svg.addEventListener("pointerdown", function (e) {
    arrasto = { x: e.clientX, y: e.clientY, vx: vb.x, vy: vb.y };
    moveu = false;
  });
  window.addEventListener("pointermove", function (e) {
    if (!arrasto) { return; }
    var caixa = svg.getBoundingClientRect();
    var dx = (e.clientX - arrasto.x) / caixa.width * vb.width;
    var dy = (e.clientY - arrasto.y) / caixa.height * vb.height;
    if (Math.abs(e.clientX - arrasto.x) + Math.abs(e.clientY - arrasto.y) > 4) { moveu = true; }
    vb.x = arrasto.vx - dx;
    vb.y = arrasto.vy - dy;
  });
  window.addEventListener("pointerup", function () { arrasto = null; });
  // arrastar por cima de uma nota não pode abri-la ao soltar
  svg.addEventListener("click", function (e) {
    if (moveu) { e.preventDefault(); moveu = false; }
  }, true);
  svg.addEventListener("dblclick", function () {
    vb.x = original.x; vb.y = original.y; vb.width = original.w; vb.height = original.h;
  });

  svg.querySelectorAll("a.no").forEach(function (no) {
    function destacar() {
      // no SVG quem vem por último fica por cima: o desenho ampliado não
      // pode ficar escondido atrás das vizinhas
      if (no.classList.contains("desenho") && no.parentNode.lastElementChild !== no) {
        no.parentNode.appendChild(no);
      }
      var perto = (no.dataset.vizinhos || "").split(" ");
      perto.push(no.dataset.id);
      svg.classList.add("focado");
      svg.querySelectorAll("a.no").forEach(function (outro) {
        outro.classList.toggle("perto", perto.indexOf(outro.dataset.id) >= 0);
      });
      svg.querySelectorAll("line").forEach(function (l) {
        l.classList.toggle("perto", l.dataset.a === no.dataset.id || l.dataset.b === no.dataset.id);
      });
    }
    function apagar() { svg.classList.remove("focado"); }
    // mouse e teclado: quem navega com Tab vê as mesmas vizinhas
    no.addEventListener("mouseenter", destacar);
    no.addEventListener("focus", destacar);
    no.addEventListener("mouseleave", apagar);
    no.addEventListener("blur", apagar);
  });
});
