"use strict";

const $ = (id) => document.getElementById(id);
const rub = (n) => new Intl.NumberFormat("ru-RU").format(n) + " ₽";
const JSON_HEADERS = { "Content-Type": "application/json" };

let rates = null;    // типы работ и уровни отделки из /api/rates
let current = null;  // последний успешный расчёт: {work_type, area, level, min, max}
let attach = false;  // приложить ли расчёт к заявке

function el(tag, text) {
  const node = document.createElement(tag);
  if (text !== undefined) node.textContent = text;  // textContent, а не innerHTML: так безопаснее
  return node;
}

// ---------- Калькулятор ----------
const typeSelect = $("work-type");
const areaNum = $("area");
const areaRange = $("area-range");

function typeInfo() {
  return rates.types.find((t) => t.id === typeSelect.value);
}

function applyType() {
  const t = typeInfo();
  for (const input of [areaNum, areaRange]) {
    input.min = t.min_area;
    input.max = t.max_area;
  }
  const clamped = Math.min(Math.max(parseInt(areaNum.value, 10) || t.min_area, t.min_area), t.max_area);
  areaNum.value = clamped;
  areaRange.value = clamped;
  $("area-hint").textContent = `От ${t.min_area} до ${t.max_area} м²`;
}

function readInputs() {
  const level = document.querySelector('input[name="level"]:checked');
  const area = parseInt(areaNum.value, 10);
  if (!level || !Number.isInteger(area)) return null;
  return { work_type: typeSelect.value, area, level: level.value };
}

let timer;
let seq = 0;  // номер запроса: устаревшие ответы игнорируем
function scheduleCalc() {
  clearTimeout(timer);
  timer = setTimeout(recalc, 250);
}

async function recalc() {
  const body = readInputs();
  if (!body) return;
  const mine = ++seq;
  $("calc-status").textContent = "Считаем…";
  try {
    const res = await fetch("/api/calc", { method: "POST", headers: JSON_HEADERS, body: JSON.stringify(body) });
    if (mine !== seq) return;
    if (!res.ok) {
      current = null;
      const t = typeInfo();
      $("calc-status").textContent = `Укажите площадь от ${t.min_area} до ${t.max_area} м².`;
      $("calc-range").textContent = "—";
      $("calc-cta").hidden = true;
      return;
    }
    const data = await res.json();
    current = { ...body, min: data.min, max: data.max };
    $("calc-status").textContent = "Ориентировочная стоимость";
    $("calc-range").textContent = `${rub(data.min)} – ${rub(data.max)}`;
    $("calc-cta").hidden = false;
    if (attach) showAttached();
  } catch {
    if (mine !== seq) return;
    $("calc-status").textContent = "Нет связи с сервером. Попробуйте ещё раз.";
  }
}

function describeCurrent() {
  const t = rates.types.find((x) => x.id === current.work_type);
  const lv = rates.levels.find((x) => x.id === current.level);
  return `Ваш расчёт: ${t.name}, ${current.area} м², ${lv.name.toLowerCase()}: ${rub(current.min)} – ${rub(current.max)}`;
}

function showAttached() {
  $("attached-text").textContent = describeCurrent();
  $("attached").hidden = false;
}

async function initCalc() {
  try {
    const res = await fetch("/api/rates");
    if (!res.ok) throw new Error("bad status");
    rates = await res.json();
  } catch {
    $("calc-status").textContent = "Не удалось загрузить калькулятор. Обновите страницу.";
    return;
  }
  const groups = {};
  for (const t of rates.types) {
    if (!groups[t.group]) {
      groups[t.group] = el("optgroup");
      groups[t.group].label = t.group;
      typeSelect.appendChild(groups[t.group]);
    }
    groups[t.group].appendChild(new Option(t.name, t.id));
  }
  rates.levels.forEach((lv, i) => {
    const label = el("label");
    label.className = "seg";
    const radio = document.createElement("input");
    radio.type = "radio";
    radio.name = "level";
    radio.value = lv.id;
    radio.checked = i === 1;  // «Стандарт» по умолчанию
    label.append(radio, el("span", lv.name));
    $("levels").appendChild(label);
  });
  typeSelect.value = "repair_capital";
  applyType();
  recalc();
}

typeSelect.addEventListener("change", () => { applyType(); scheduleCalc(); });
areaRange.addEventListener("input", () => { areaNum.value = areaRange.value; scheduleCalc(); });
areaNum.addEventListener("input", () => { areaRange.value = areaNum.value; scheduleCalc(); });
$("levels").addEventListener("change", scheduleCalc);
$("calc-form").addEventListener("submit", (e) => e.preventDefault());

$("calc-cta").addEventListener("click", () => {
  if (!current) return;
  attach = true;
  showAttached();
  location.hash = "#request";
  $("f-name").focus({ preventScroll: true });
});
$("attached-remove").addEventListener("click", () => {
  attach = false;
  $("attached").hidden = true;
});

initCalc();

// ---------- Форма заявки -> POST /api/lead ----------
const form = $("lead-form");
const errorBox = $("form-error");
const submitBtn = $("submit-btn");

form.addEventListener("submit", async (event) => {
  event.preventDefault();
  const name = $("f-name").value.trim();
  const phone = $("f-phone").value;
  const comment = $("f-comment").value.trim();
  const consent = $("f-consent").checked;
  const website = $("f-website").value;

  if (name.length < 2) { errorBox.textContent = "Введите имя."; return; }
  if (phone.replace(/\D/g, "").length < 10) { errorBox.textContent = "Введите телефон полностью, не меньше 10 цифр."; return; }
  if (!consent) { errorBox.textContent = "Поставьте галочку согласия, иначе заявку отправить нельзя."; return; }

  const payload = { name, phone, comment, consent, website };
  if (attach && current) {
    payload.work_type = current.work_type;
    payload.area = current.area;
    payload.level = current.level;
  }

  errorBox.textContent = "";
  submitBtn.disabled = true;
  submitBtn.textContent = "Отправляем…";
  try {
    const res = await fetch("/api/lead", { method: "POST", headers: JSON_HEADERS, body: JSON.stringify(payload) });
    if (res.status === 429) {
      errorBox.textContent = "Слишком много заявок. Попробуйте позже.";
    } else if (!res.ok) {
      errorBox.textContent = "Проверьте введённые данные.";
    } else {
      form.hidden = true;
      $("form-ok").hidden = false;
    }
  } catch {
    errorBox.textContent = "Нет связи с сервером. Попробуйте ещё раз.";
  } finally {
    submitBtn.disabled = false;
    submitBtn.textContent = "Отправить заявку";
  }
});
