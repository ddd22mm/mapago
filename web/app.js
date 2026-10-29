"use strict";
const $ = (id) => document.getElementById(id);
let game = null,
  selected = null,
  busy = false,
  resultShown = false;
const winds = ["東", "南", "西", "北"],
  names = ["나", "AI 1", "AI 2", "AI 3"];
const labels = {
  E: "동",
  S: "남",
  W: "서",
  N: "북",
  P: "백",
  F: "발",
  C: "중",
};
const numbers = ["", "一", "二", "三", "四", "五", "六", "七", "八", "九"];
function el(tag, cls, text) {
  const e = document.createElement(tag);
  if (cls) e.className = cls;
  if (text !== undefined) e.textContent = text;
  return e;
}
function code(id) {
  if (id >= 108)
    return ["E", "S", "W", "N", "P", "F", "C"][Math.floor((id - 108) / 4)];
  return `${Math.floor((id % 36) / 4) + 1}${["m", "p", "s"][Math.floor(id / 36)]}${[16, 52, 88].includes(id) ? "r" : ""}`;
}
function tileName(c) {
  if (labels[c]) return labels[c];
  return `${c[0]}${{ m: "만", p: "통", s: "삭" }[c[1]]}${c.endsWith("r") ? " (적도라)" : ""}`;
}
function tile(c, tag = "span") {
  const node = el(tag, "tile");
  node.setAttribute("aria-label", tileName(c));
  node.title = tileName(c);
  if (c.endsWith("r")) node.classList.add("red-five");
  if (labels[c]) {
    if (c === "F") node.classList.add("green");
    if (c === "C") node.classList.add("red");
    node.append(
      el(
        "span",
        "honor",
        { E: "東", S: "南", W: "西", N: "北", P: "白", F: "發", C: "中" }[c],
      ),
    );
  } else if (c[1] === "m") {
    node.append(
      el("span", "man-number", numbers[+c[0]]),
      el("span", "man-suit", "萬"),
    );
  } else {
    const n = +c[0],
      svg = document.createElementNS("http://www.w3.org/2000/svg", "svg");
    svg.setAttribute("viewBox", "0 0 36 54");
    svg.setAttribute("aria-hidden", "true");
    const pts =
      n === 1
        ? [[18, 27]]
        : n === 2
          ? [
              [18, 13],
              [18, 41],
            ]
          : n === 3
            ? [
                [10, 12],
                [18, 27],
                [26, 42],
              ]
            : n === 4
              ? [
                  [9, 13],
                  [27, 13],
                  [9, 41],
                  [27, 41],
                ]
              : n === 5
                ? [
                    [9, 12],
                    [27, 12],
                    [18, 27],
                    [9, 42],
                    [27, 42],
                  ]
                : n === 6
                  ? [
                      [9, 10],
                      [27, 10],
                      [9, 27],
                      [27, 27],
                      [9, 44],
                      [27, 44],
                    ]
                  : n === 7
                    ? [
                        [9, 9],
                        [18, 19],
                        [27, 9],
                        [9, 33],
                        [27, 33],
                        [9, 46],
                        [27, 46],
                      ]
                    : n === 8
                      ? [
                          [9, 8],
                          [27, 8],
                          [9, 21],
                          [27, 21],
                          [9, 34],
                          [27, 34],
                          [9, 47],
                          [27, 47],
                        ]
                      : [
                          [8, 9],
                          [18, 9],
                          [28, 9],
                          [8, 27],
                          [18, 27],
                          [28, 27],
                          [8, 45],
                          [18, 45],
                          [28, 45],
                        ];
    for (const [x, y] of pts) {
      const part = document.createElementNS(
        svg.namespaceURI,
        c[1] === "p" ? "circle" : "rect",
      );
      if (c[1] === "p") {
        part.setAttribute("cx", x);
        part.setAttribute("cy", y);
        part.setAttribute("r", n === 1 ? 10 : 4);
        part.setAttribute("fill", "none");
        part.setAttribute(
          "stroke",
          c.endsWith("r")
            ? "#be493b"
            : n === 1 || y === 27
              ? "#a84136"
              : "#264e63",
        );
        part.setAttribute("stroke-width", 2.5);
      } else {
        part.setAttribute("x", x - 2);
        part.setAttribute("y", y - 5);
        part.setAttribute("width", 4);
        part.setAttribute("height", 10);
        part.setAttribute("rx", 1.5);
        part.setAttribute("fill", c.endsWith("r") ? "#b94335" : "#276c50");
      }
      svg.append(part);
    }
    node.append(svg);
  }
  node.append(el("small", "tile-code", c));
  return node;
}
async function request(path, body) {
  const response = await fetch(path, {
    method: body === undefined ? "GET" : "POST",
    headers: body === undefined ? {} : { "Content-Type": "application/json" },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  const data = await response.json();
  if (!response.ok) {
    const error = new Error(data.error || "대국에 연결할 수 없습니다.");
    error.status = response.status;
    throw error;
  }
  return data;
}
function error(message) {
  $("notice-text").textContent = message;
  $("notice").hidden = false;
}
function setBusy(value) {
  busy = value;
  $("new-game").disabled = value;
  $("confirm-start").disabled = value;
  $("table").setAttribute("aria-busy", String(value));
  if (value)
    for (const node of document.querySelectorAll(
      "#actions button, #hand button",
    ))
      node.disabled = true;
}
function actionText(a) {
  return (
    a.label +
    (a.tile ? ` · ${tileName(a.tile)}` : "") +
    (a.consumed.length ? ` (${a.consumed.map(tileName).join(" ")})` : "")
  );
}
function renderActions() {
  const actions = $("actions");
  actions.replaceChildren();
  if (!game) return;
  if (game.status === "finished") {
    const b = el("button", "button primary", "대국 결과 보기");
    b.onclick = () => $("result-dialog").showModal();
    actions.append(b);
    return;
  }
  const discards = game.actions.filter((a) => a.kind === 0),
    available = discards.find((a) => a.tile_id === selected);
  $("selected-label").textContent = available
    ? `${tileName(available.tile)} 선택 · 타패하면 되돌릴 수 없어요.`
    : discards.length
      ? "버릴 패를 선택해 주세요."
      : "가능한 행동을 선택해 주세요.";
  for (const a of game.actions.filter((a) => a.kind !== 0)) {
    const b = el(
      "button",
      `button ${[4, 6].includes(a.kind) ? "primary" : "subtle"}`,
      actionText(a),
    );
    b.onclick = () => submit(a.id);
    b.disabled = busy;
    actions.append(b);
  }
  if (discards.length) {
    const b = el(
      "button",
      "button primary",
      available ? `${tileName(available.tile)} 타패` : "타패",
    );
    b.id = "discard";
    b.disabled = busy || !available;
    b.onclick = () => submit(available.id);
    actions.append(b);
  }
}
function eventText(e) {
  const who = names[e.actor] || "";
  return e.type === "dahai"
    ? `${who} · ${tileName(e.pai)} 타패`
    : e.type === "start_kyoku"
      ? "동1국 · 패를 받았습니다"
      : e.type === "reach"
        ? `${who} · 리치 선언`
        : e.type === "reach_accepted"
          ? `${who} · 리치 확정`
          : e.type === "hora"
            ? `${who} · ${e.actor === e.target ? "쯔모 화료" : "론 화료"}`
            : e.type === "ryukyoku"
              ? `유국 · ${{ exhaustive_draw: "패산 소진", kyushukyuhai: "구종구패" }[e.reason] || "국 종료"}`
              : {
                  chi: `${who} · 치`,
                  pon: `${who} · 퐁`,
                  ankan: `${who} · 암깡`,
                  kakan: `${who} · 가깡`,
                  daiminkan: `${who} · 대명깡`,
                  dora: "새 도라 표시패",
                  end_game: "한 국을 마쳤습니다",
                }[e.type];
}
function render() {
  if (!game) return;
  const s = game.state,
    done = game.status === "finished",
    hand = s.hands[0],
    discards = game.actions.filter((a) => a.kind === 0);
  $("table-empty").hidden = true;
  $("notice").hidden = true;
  $("round-label").textContent =
    `${{ E: "동", S: "남", W: "서", N: "북" }[game.round.bakaze]}${game.round.kyoku}국`;
  $("center-round").textContent =
    `${game.round.bakaze === "E" ? "東" : "南"}${numbers[game.round.kyoku]}局`;
  $("rule-label").textContent =
    game.rule === "tenhou" ? "천봉 프리셋" : "작혼 프리셋";
  $("status-label").textContent = done ? "한 국 종료" : "당신의 차례";
  $("remaining").textContent = game.remaining;
  $("honba").textContent = `${s.honba} 본장`;
  $("sticks").textContent = `공탁 ${s.riichi_sticks}`;
  $("hand-title").textContent = done ? "한 국 종료" : "나의 손패";
  $("hand-hint").textContent = done
    ? "수고하셨습니다."
    : discards.length
      ? "버릴 패를 선택하세요."
      : "호출 또는 패스를 선택하세요.";
  $("hand-count").textContent = `${hand.length}장`;
  if (!discards.some((a) => a.tile_id === selected))
    selected = discards.some((a) => a.tile_id === hand.at(-1))
      ? hand.at(-1)
      : (discards[0]?.tile_id ?? null);
  $("hand").replaceChildren();
  const sorted = [...hand].sort((a, b) => a - b);
  let drawn = null;
  // Separate the actual most recent own draw only when it is still in hand.
  const ownDraw = [...game.events]
    .reverse()
    .find((item) => item.event.type === "tsumo" && item.event.actor === 0);
  if (ownDraw && hand.length % 3 === 2 && discards.length) {
    const candidate = hand.at(-1);
    if (code(candidate) === ownDraw.event.pai) drawn = candidate;
  }
  if (drawn !== null) {
    sorted.splice(sorted.indexOf(drawn), 1);
    sorted.push(drawn);
  }
  for (const id of sorted) {
    const t = tile(code(id), "button");
    t.type = "button";
    t.disabled = busy || !discards.some((a) => a.tile_id === id);
    t.classList.toggle("selected", id === selected);
    t.classList.toggle("drawn", id === drawn);
    t.setAttribute("aria-pressed", String(id === selected));
    t.onclick = () => {
      selected = id;
      render();
    };
    $("hand").append(t);
  }
  $("dora").replaceChildren(...s.dora_indicators.map((id) => tile(code(id))));
  $("own-melds").replaceChildren();
  $("score-list").replaceChildren();
  for (let seat = 0; seat < 4; seat++) {
    const score = s.scores[seat].toLocaleString("ko-KR"),
      row = el("div", `score-row ${seat === 0 ? "mine" : ""}`);
    row.append(
      el("span", "score-wind", winds[seat]),
      el("span", "", names[seat]),
    );
    if (seat === 0) row.append(el("small", "", "나"));
    if (s.riichi_declared[seat]) row.append(el("small", "", "리치"));
    row.append(el("span", "score-number", score));
    $("score-list").append(row);
    if (seat === 0) $("self-score").textContent = score;
    else {
      $(`table-score-${seat}`).textContent = score;
      const count = 13 - s.melds[seat].length * 3;
      $(`backs-${seat}`).replaceChildren(
        ...Array.from({ length: Math.max(0, count) }, () =>
          el("span", "back-tile"),
        ),
      );
      $(`melds-${seat}`).replaceChildren();
    }
    $(`river-${seat}`).replaceChildren(
      ...s.discards[seat].map((id) => tile(code(id))),
    );
    for (const meld of s.melds[seat]) {
      const group = el("div", "");
      group.title = "공개된 후로";
      group.append(...meld.tiles.map((id) => tile(code(id))));
      (seat === 0 ? $("own-melds") : $(`melds-${seat}`)).append(group);
    }
  }
  $("policy-label").textContent =
    game.bot_policy === "rule-based"
      ? "규칙 기반 샹텐·유효패 봇"
      : game.bot_policy === "random-legal"
        ? "랜덤 합법 행동 봇"
        : "첫 번째 합법 행동 봇";
  $("timeline").replaceChildren();
  for (const item of [...game.events].reverse()) {
    const text = eventText(item.event);
    if (!text) continue;
    const li = el("li", "", text);
    li.append(el("small", "", `#${item.seq}`));
    $("timeline").append(li);
    if ($("timeline").children.length >= 15) break;
  }
  renderActions();
  $("announcer").textContent = done
    ? "한 국이 끝났습니다."
    : `당신의 차례입니다. ${discards.length ? "버릴 패를 선택해 주세요." : "가능한 행동을 선택해 주세요."}`;
  if (done && !resultShown) {
    resultShown = true;
    showResult();
  }
}
function showResult() {
  const r = game.result,
    e = [...game.events]
      .reverse()
      .find((x) => ["hora", "ryukyoku"].includes(x.event.type))?.event;
  $("result-title").textContent =
    e?.type === "hora"
      ? `${names[e.actor]}의 ${e.actor === e.target ? "쯔모" : "론"} 화료`
      : "유국으로 한 국을 마쳤어요.";
  $("result-description").textContent =
    "한 국 연습이 끝났습니다. 점수 변화와 나의 대국 기록을 확인하세요.";
  $("result-scores").replaceChildren();
  for (let i = 0; i < 4; i++) {
    const card = el("div", `result-score ${i === 0 ? "mine" : ""}`);
    card.append(
      el("span", "", names[i]),
      el("strong", "", r.scores[i].toLocaleString("ko-KR")),
      el(
        "small",
        "",
        `${r.scores[i] - 25000 >= 0 ? "+" : ""}${r.scores[i] - 25000}점`,
      ),
    );
    $("result-scores").append(card);
  }
  $("result-dialog").showModal();
}
async function submit(id) {
  if (busy || !game) return;
  setBusy(true);
  try {
    game = await request("/api/action", {
      revision: game.revision,
      action_id: id,
    });
    selected = null;
  } catch (e) {
    if (e.status === 409) {
      try {
        game = await request("/api/game");
      } catch {}
    }
    error(e.message);
  } finally {
    setBusy(false);
    const message = $("notice").hidden ? null : $("notice-text").textContent;
    render();
    if (message) error(message);
  }
}
async function recover() {
  setBusy(true);
  let recovered = false;
  try {
    game = await request("/api/game");
    recovered = true;
  } catch (e) {
    if (e.status === 404) {
      game = null;
      $("table-empty").hidden = false;
    } else
      error(
        "서버에 연결할 수 없습니다. 실행 상태를 확인한 뒤 다시 연결해 주세요.",
      );
  } finally {
    setBusy(false);
    if (recovered) render();
  }
}
function setup() {
  $("result-dialog").close();
  $("setup-dialog").showModal();
}
$("new-game").onclick = setup;
$("start-table").onclick = setup;
$("play-again").onclick = setup;
$("cancel-setup").onclick = () => $("setup-dialog").close();
$("close-result").onclick = () => $("result-dialog").close();
$("retry").onclick = recover;
$("setup-form").onsubmit = async (e) => {
  e.preventDefault();
  if (busy) return;
  setBusy(true);
  try {
    game = await request("/api/game", {
      rule: $("rule").value,
      policy: $("policy").value,
    });
    resultShown = false;
    selected = null;
    $("setup-dialog").close();
    setBusy(false);
    render();
  } catch (err) {
    $("setup-dialog").close();
    error(err.message);
  } finally {
    setBusy(false);
  }
};
$("download").onclick = async () => {
  try {
    const record = await request("/api/replay");
    const url = URL.createObjectURL(
      new Blob([JSON.stringify(record, null, 2)], { type: "application/json" }),
    );
    const a = el("a", "");
    a.href = url;
    a.download = "mapago-my-hand.json";
    a.click();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
  } catch (e) {
    error(e.message);
  }
};
document.addEventListener("keydown", (e) => {
  if (
    busy ||
    !game ||
    document.querySelector("dialog[open]") ||
    ["SELECT", "INPUT", "TEXTAREA"].includes(e.target.tagName)
  )
    return;
  const ds = game.actions.filter((a) => a.kind === 0);
  if (e.key === "ArrowLeft" || e.key === "ArrowRight") {
    e.preventDefault();
    if (ds.length) {
      const ids = [...game.state.hands[0]]
        .sort((a, b) => a - b)
        .filter((id) => ds.some((a) => a.tile_id === id));
      const idx = ids.indexOf(selected);
      selected =
        ids[
          (idx + (e.key === "ArrowRight" ? 1 : -1) + ids.length) % ids.length
        ];
      render();
    }
  } else if (e.key.toLowerCase() === "d") {
    const a = ds.find((a) => a.tile_id === selected);
    if (a) {
      e.preventDefault();
      submit(a.id);
    }
  } else if (e.key === "Escape") {
    const a = game.actions.find((a) => a.kind === 7);
    if (a) {
      e.preventDefault();
      submit(a.id);
    }
  }
});
for (let seat = 1; seat < 4; seat++)
  $(`backs-${seat}`).replaceChildren(
    ...Array.from({ length: 13 }, () => el("span", "back-tile")),
  );
recover();
