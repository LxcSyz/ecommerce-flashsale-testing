"use strict";
const $ = (id) => document.getElementById(id);
let token = sessionStorage.getItem("tradelab-token") || "";
let cart = [];
const pendingKeys = new Map();
const money = (cents) => `¥${(cents / 100).toFixed(2)}`;
function notify(text, error = false) { $("message").textContent = text; $("message").classList.toggle("error", error); }
async function api(path, method = "GET", body, key) {
  const headers = { "Content-Type": "application/json" };
  if (token) headers.Authorization = `Bearer ${token}`;
  if (key) headers["Idempotency-Key"] = key;
  const response = await fetch(`/api${path}`, { method, headers, body: body === undefined ? undefined : JSON.stringify(body) });
  const data = await response.json();
  if (!response.ok) throw new Error(`${data.error.code}：${data.error.message}`);
  return data;
}
function element(tag, text, className) {
  const node = document.createElement(tag);
  if (text !== undefined) node.textContent = text;
  if (className) node.className = className;
  return node;
}
function button(text, action, secondary = false) {
  const node = element("button", text, secondary ? "secondary" : "");
  node.type = "button";
  node.addEventListener("click", async () => {
    node.disabled = true;
    try { await action(); } catch (error) { notify(error.message, true); }
    finally { node.disabled = false; }
  });
  return node;
}
async function submitOrder(items, flash = false) {
  const signature = JSON.stringify([flash, items]);
  // Preserve the key on transport errors, so retrying cannot create another order.
  if (!pendingKeys.has(signature)) pendingKeys.set(signature, crypto.randomUUID());
  const order = await api(flash ? "/flash-sale/orders" : "/orders", "POST", { items }, pendingKeys.get(signature));
  pendingKeys.delete(signature);
  notify(`订单 #${order.id} 创建成功，已预占库存，待模拟支付。`);
  await refresh();
}
async function loadProducts() {
  const products = await api("/products");
  $("products").replaceChildren();
  for (const product of products) {
    const flash = product.kind === "flash";
    const card = element("article", undefined, `product${flash ? " flash" : ""}`);
    card.dataset.productId = product.id;
    card.append(element("div", { 1: "⌨", 2: "♫", 3: "◉" }[product.id], "symbol"));
    if (flash) card.append(element("span", "限时秒杀 · 每人 1 件", "tag"));
    card.append(element("h3", product.name), element("div", money(product.price_cents), "price"),
      element("p", `剩余库存：${product.stock} / ${product.initial_stock}`, "stock"));
    if (flash) card.append(element("p", `截止：${new Date(product.ends_at * 1000).toLocaleString()}`, "muted"));
    card.append(button(flash ? "立即抢购" : "加入购物车", async () => {
      if (!token) throw new Error("请先登录");
      if (flash) return submitOrder([{ product_id: product.id, quantity: 1 }], true);
      const old = cart.find((item) => item.product_id === product.id);
      await api("/cart", "POST", { product_id: product.id, quantity: (old?.quantity || 0) + 1 });
      await loadAccount(); notify("已加入购物车");
    }));
    $("products").append(card);
  }
}
async function loadAccount() {
  $("auth-form").hidden = Boolean(token); $("logout").hidden = !token;
  if (!token) {
    cart = []; $("identity").textContent = "尚未登录";
    $("cart").textContent = "登录后查看购物车"; $("orders").textContent = "登录后查看订单"; return;
  }
  const me = await api("/me");
  $("identity").textContent = `你好，${me.username}`;
  cart = await api("/cart");
  $("cart").replaceChildren();
  if (!cart.length) $("cart").textContent = "购物车为空";
  cart.forEach((item) => {
    const row = element("div", undefined, "cart-row");
    row.append(element("span", `${item.name} × ${item.quantity}`), button("移除", async () => {
      await api(`/cart/${item.product_id}`, "DELETE"); await loadAccount();
    }, true));
    $("cart").append(row);
  });
  const orders = await api("/orders");
  $("orders").replaceChildren();
  if (!orders.length) $("orders").textContent = "暂无订单，先选一件商品吧。";
  for (const order of orders) {
    const card = element("article", undefined, "order"); card.dataset.orderId = order.id;
    const details = element("div");
    details.append(element("strong", `订单 #${order.id} · ${money(order.total_cents)}`),
      element("p", `${order.kind === "flash" ? "秒杀" : "普通"}订单 · ${order.items.reduce((sum, item) => sum + item.quantity, 0)} 件商品`, "muted"));
    const actions = element("div", undefined, "actions");
    actions.append(element("span", { pending: "待支付", paid: "已支付", cancelled: "已取消" }[order.status], "status"));
    if (order.status === "pending") {
      for (const [action, label] of [["pay", "模拟支付"], ["cancel", "取消订单"]]) {
        actions.append(button(label, async () => {
          await api(`/orders/${order.id}/${action}`, "POST", {});
          notify(action === "pay" ? "模拟支付成功" : "订单已取消，库存已回补"); await refresh();
        }, action === "cancel"));
      }
    }
    card.append(details, actions); $("orders").append(card);
  }
}
async function refresh() { await loadProducts(); await loadAccount(); }
function credentials() { return { username: $("username").value, password: $("password").value }; }
async function authenticate(register) {
  if (!$("auth-form").reportValidity()) return;
  try {
    if (register) await api("/auth/register", "POST", credentials());
    const result = await api("/auth/login", "POST", credentials());
    token = result.token; sessionStorage.setItem("tradelab-token", token); $("password").value = "";
    await refresh(); notify(register ? "注册成功，已登录" : "登录成功");
  } catch (error) { notify(error.message, true); }
}
$("auth-form").addEventListener("submit", (event) => { event.preventDefault(); authenticate(false); });
$("register").onclick = () => authenticate(true);
$("logout").onclick = () => { token = ""; sessionStorage.removeItem("tradelab-token"); pendingKeys.clear(); loadAccount(); notify("已退出本页面登录"); };
$("checkout").onclick = async () => {
  try {
    if (!cart.length) throw new Error("请先登录并添加商品");
    await submitOrder(cart.map(({ product_id, quantity }) => ({ product_id, quantity })));
  } catch (error) { notify(error.message, true); }
};
$("refresh").onclick = () => refresh().catch((error) => notify(error.message, true));
refresh().catch((error) => notify(error.message, true));
