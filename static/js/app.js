// Dicas dinâmicas do formulário. A página funciona sem este script; ele só melhora a leitura.
(function () {
  var elCulturas = document.getElementById("dados-culturas");
  var elSolos = document.getElementById("dados-solos");
  if (!elCulturas || !elSolos) return;
  var culturas = JSON.parse(elCulturas.textContent);
  var solos = JSON.parse(elSolos.textContent);
  var num = function (x) { return String(x).replace(".", ","); };

  var selCultura = document.getElementById("cultura");
  var selSolo = document.getElementById("solo");
  var semeadura = document.getElementById("data_semeadura");
  var dicaCultura = document.getElementById("dica-cultura");
  var dicaSolo = document.getElementById("dica-solo");
  var dicaCiclo = document.getElementById("dica-ciclo");

  function atualizar() {
    var c = culturas[selCultura.value];
    var s = solos[selSolo.value];
    if (c) {
      dicaCultura.textContent = "Ciclo de " + c.ciclo + " dias · raízes até " + num(c.zr) +
        " m · fator de depleção p = " + num(c.p);
    }
    if (s) {
      dicaSolo.textContent = "Capacidade de campo " + num(s.fc) + " m³/m³ · ponto de murcha " + num(s.wp) + " m³/m³";
    }
    if (c && semeadura.value) {
      var fim = new Date(semeadura.value + "T00:00:00");
      fim.setDate(fim.getDate() + c.ciclo - 1);
      dicaCiclo.textContent = "Com esta data, o ciclo termina em " + fim.toLocaleDateString("pt-BR") + ".";
    }
  }

  [selCultura, selSolo, semeadura].forEach(function (el) { el.addEventListener("change", atualizar); });
  atualizar();
})();

// Localização: alterna entre referência, município e coordenadas, e sugere municípios ao digitar.
// Sem este script os três grupos de campos ficam visíveis e o formulário continua funcionando.
(function () {
  var grupo = document.getElementById("grupo-local");
  if (!grupo) return;
  var radios = grupo.querySelectorAll('input[name="local_modo"]');
  var blocos = grupo.querySelectorAll("[data-local]");

  function mostrar() {
    var modo = "referencia";
    radios.forEach(function (r) { if (r.checked) modo = r.value; });
    blocos.forEach(function (b) { b.hidden = b.getAttribute("data-local") !== modo; });
  }
  radios.forEach(function (r) { r.addEventListener("change", mostrar); });
  mostrar();

  var campo = document.getElementById("municipio");
  var uf = document.getElementById("uf");
  var lista = document.getElementById("lista-municipios");
  var timer = null;
  if (!campo || !lista || !window.fetch) return;

  campo.addEventListener("input", function () {
    clearTimeout(timer);
    var texto = campo.value.trim();
    if (texto.length < 3 || / – [A-Za-z]{2}$/.test(texto)) return;
    timer = setTimeout(function () {
      var url = "/api/municipios?q=" + encodeURIComponent(texto) + (uf.value ? "&uf=" + uf.value : "");
      fetch(url).then(function (r) { return r.ok ? r.json() : []; }).then(function (itens) {
        lista.innerHTML = "";
        (Array.isArray(itens) ? itens : []).forEach(function (m) {
          var o = document.createElement("option");
          o.value = m.rotulo;
          lista.appendChild(o);
        });
      }).catch(function () { /* sem sugestões: o servidor ainda resolve o texto digitado */ });
    }, 300);
  });
})();
