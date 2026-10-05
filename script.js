/* =====================================================================
   FEIRA NUZZI — FRONT-END CLIENTE
   ===================================================================== */

// O catálogo não guarda mais lojas/produtos fixos aqui.
// STALLS agora é preenchido 100% a partir do banco de dados,
// via GET /api/stalls (ver refreshVendorStalls()).
let STALLS = [];

function registerVisit(id) {
    fetch("/api/visits", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        credentials: "include",
        body: JSON.stringify({ stallId: id }),
    }).catch(() => { });
}

function escHtml(s) {
    return String(s ?? "").replace(/[&<>"']/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
}

function getCategories() {
    return ["Todas", ...new Set(STALLS.map(s => s.category))];
}

const filtersEl = document.getElementById("filters");
const gridEl = document.getElementById("grid");
const overlay = document.getElementById("overlay");
const panel = document.getElementById("panel");
const searchInput = document.getElementById("searchInput");

let activeCat = "Todas";
let searchTerm = "";

function renderFilters() {
    const categories = getCategories();
    filtersEl.innerHTML = categories.map(c =>
        `<button data-cat="${c}" class="${c === activeCat ? 'active' : ''}">${c}</button>`
    ).join('');
    filtersEl.querySelectorAll("button").forEach(btn => {
        btn.addEventListener("click", () => {
            activeCat = btn.dataset.cat;
            renderFilters();
            renderGrid();
        });
    });
}

function renderGrid() {
    let list = activeCat === "Todas" ? STALLS : STALLS.filter(s => s.category === activeCat);
    const term = searchTerm.trim().toLowerCase();
    if (term) {
        list = list.filter(s =>
            s.name.toLowerCase().includes(term) ||
            s.category.toLowerCase().includes(term) ||
            s.desc.toLowerCase().includes(term) ||
            s.products.some(p => p.name.toLowerCase().includes(term))
        );
    }
    if (list.length === 0) {
        gridEl.innerHTML = `<p style="grid-column:1/-1; text-align:center; padding:40px 0; color:#6b5f4d;">Nenhuma barraca encontrada.</p>`;
        return;
    }
    gridEl.innerHTML = list.map(s => `
        <div class="stall-card" data-id="${s.id}">
            <span class="tag">${s.category}</span>
            <img src="${s.cover}" alt="${s.name}">
            <div class="body">
                <h3>${s.name}</h3>
                <div class="loc">📍 ${s.address.split('—')[0].trim()}</div>
                <div class="desc">${s.desc}</div>
                <div class="more">Saiba mais →</div>
            </div>
        </div>
    `).join('');
    gridEl.querySelectorAll('.stall-card').forEach(card => {
        card.addEventListener('click', async () => {
            const id = Number(card.dataset.id);
            // Busca o estoque/produtos mais recentes antes de abrir a barraca,
            // pra não mostrar um número desatualizado de quando a página carregou.
            await refreshVendorStalls();
            openStall(id);
        });
    });
}

function openStall(id) {
    const s = STALLS.find(x => x.id === id);
    if (!s) return;
    registerVisit(id);
    panel.innerHTML = `
        <div class="panel-head">
            <button class="close" id="closeBtn">✕</button>
            <div class="gallery">
                <img src="${s.gallery[0]}" alt="${s.name}">
                <div class="side">
                    <img src="${s.gallery[1]}" alt="${s.name} detalhe 1">
                    <img src="${s.gallery[2]}" alt="${s.name} detalhe 2">
                </div>
            </div>
        </div>
        <div class="panel-body">
            <span class="tag">${s.category}</span>
            <h2>${s.name}</h2>
            <div class="owner">por ${s.owner}</div>
            <p class="about">${s.about}</p>

            <div class="loc-block">
                <div class="pin">📍</div>
                <div class="info">
                    <b>${s.address}</b>
                    <span>Localização dentro da feira</span>
                    <div class="hours">🕒 ${s.hours}</div>
                </div>
            </div>

            <div class="section-label">Produtos</div>
            <div class="products">
                ${s.products.length ? s.products.map((p, i) => {
                    const temControle = p.estoque !== undefined && p.estoque !== null;
                    const semEstoque = temControle && Number(p.estoque) <= 0;
                    const estoqueBaixo = temControle && !semEstoque && Number(p.estoque) <= 3;
                    let estoqueInfo = "";
                    if (semEstoque) estoqueInfo = `<div class="stock-info stock-out">Esgotado</div>`;
                    else if (estoqueBaixo) estoqueInfo = `<div class="stock-info stock-low">Só ${p.estoque} ${p.estoque === 1 ? 'unidade' : 'unidades'} restantes</div>`;
                    else if (temControle) estoqueInfo = `<div class="stock-info">${p.estoque} em estoque</div>`;
                    const cfg = !!(p.configuravel && p.opcoes);
                    const precoHtml = cfg
                        ? `<span class="price-from">a partir de</span>${formatBRL(precoMinimo(p))}`
                        : p.price;
                    return `
                    <div class="product">
                        <img src="${p.img}" alt="${p.name}">
                        <div class="pbody">
                            <h4>${p.name}</h4>
                            <div class="price">${precoHtml}</div>
                            <p>${p.desc}</p>
                            ${estoqueInfo}
                            ${semEstoque
                            ? `<button class="product-add" disabled>Esgotado</button>`
                            : `<button class="product-add" data-stall="${s.id}" data-idx="${i}"${cfg ? ' data-config="1"' : ''}>${cfg ? 'Escolher sabor e tamanho' : '+ Adicionar ao carrinho'}</button>`
                        }
                        </div>
                    </div>
                `;
                }).join('') : `<p style="color:#6b5f4d;">Nenhum produto disponível no momento.</p>`}
            </div>
        </div>
    `;
    overlay.classList.add('open');
    document.getElementById('closeBtn').addEventListener('click', closeStall);
    panel.querySelectorAll('.product-add:not([disabled])').forEach(btn => {
        btn.addEventListener('click', () => {
            const stallId = Number(btn.getAttribute('data-stall'));
            const idx = parseInt(btn.getAttribute('data-idx'), 10);
            if (btn.hasAttribute('data-config')) {
                // produto configurável: abre o seletor de sabor/tamanho/adicionais
                if (!requireLoginForCartAction({ type: "configure", stallId, idx })) return;
                openConfigurator(stallId, idx, btn);
                return;
            }
            if (!requireLoginForCartAction({ type: "add-to-cart", stallId, idx })) return;
            addToCart(stallId, idx);
            btn.textContent = '✓ Adicionado';
            btn.classList.add('added');
            setTimeout(() => {
                btn.textContent = '+ Adicionar ao carrinho';
                btn.classList.remove('added');
            }, 1200);
        });
    });
    document.body.style.overflow = 'hidden';
}

function closeStall() {
    overlay.classList.remove('open');
    document.body.style.overflow = '';
}

overlay.addEventListener('click', (e) => { if (e.target === overlay) closeStall(); });

document.addEventListener('keydown', (e) => {
    if (e.key === 'Escape') {
        closeConfigurator();
        closeStall();
        closeCart();
        closeConfirm();
        closeTicket();
    }
});

searchInput.addEventListener('input', (e) => {
    searchTerm = e.target.value;
    renderGrid();
});

async function refreshVendorStalls() {
    // O catálogo é 100% dinâmico: a cada atualização, busca o estado
    // atual das lojas/produtos diretamente do banco (via /api/stalls)
    // e substitui a lista inteira — nada fica "preso" do carregamento anterior.
    try {
        const r = await fetch("/api/stalls", { credentials: "include" });
        if (!r.ok) {
            STALLS = [];
            return;
        }
        const lista = await r.json();
        STALLS = Array.isArray(lista) ? lista : [];
    } catch (e) {
        console.warn("Falha ao carregar barracas do banco de dados:", e);
        STALLS = [];
    }
}

function getCart() {
    try { return JSON.parse(localStorage.getItem('feira_cart') || '[]'); }
    catch (e) { return []; }
}
function saveCart(cart) {
    localStorage.setItem('feira_cart', JSON.stringify(cart));
    updateCartBadge();
}
function parsePrice(priceStr) {
    const match = String(priceStr).match(/[\d.,]+/);
    if (!match) return 0;
    return parseFloat(match[0].replace(/\./g, '').replace(',', '.')) || 0;
}
function formatBRL(value) {
    return 'R$ ' + Number(value).toFixed(2).replace('.', ',');
}

function addToCart(stallId, productIdx) {
    const stall = STALLS.find(s => s.id === stallId);
    if (!stall) return;
    const product = stall.products[productIdx];
    if (!product) return;

    const cart = getCart();
    const key = `${stallId}__${productIdx}`;
    const existing = cart.find(item => item.key === key);

  if (existing) {
    existing.qty += 1;
} else {
    cart.push({
        key,
        stallId,
        stallName: stall.name,
        stallAddress: stall.address,
        productId: product.id || null,
        name: product.name,
        price: product.price,
        img: product.img,
        qty: 1
    });
}
    saveCart(cart);
}
/* =====================================================================
   PRODUTO CONFIGURÁVEL (ex.: milk-shake): Sabor → Tamanho → Adicionais
   O preço mostrado aqui é só uma prévia: o servidor recalcula
   (preço base + acréscimo do tamanho + adicionais) ao registrar o pedido.
   ===================================================================== */
const configOverlay = document.getElementById('configOverlay');
const configPanel = document.getElementById('configPanel');
let _cfgCtx = null;

function precoMinimo(product) {
    const tams = (product.opcoes && product.opcoes.tamanhos) || [];
    const menor = tams.length ? Math.min(...tams.map(t => Number(t.acrescimo) || 0)) : 0;
    return parsePrice(product.price) + menor;
}

function calcPrecoConfig(product, ctx) {
    const op = product.opcoes;
    const tam = op.tamanhos.find(t => t.id === ctx.tamanhoId);
    const adds = op.adicionais.filter(a => ctx.adicionais.has(a.id));
    return parsePrice(product.price)
        + (tam ? Number(tam.acrescimo) || 0 : 0)
        + adds.reduce((soma, a) => soma + (Number(a.preco) || 0), 0);
}

function openConfigurator(stallId, idx, btn) {
    const stall = STALLS.find(s => s.id === stallId);
    const product = stall && stall.products[idx];
    if (!product || !product.opcoes) return;
    const op = product.opcoes;

    _cfgCtx = {
        stallId, idx, btn: btn || null,
        saborId: op.sabores.length === 1 ? op.sabores[0].id : null,
        tamanhoId: op.tamanhos.length === 1 ? op.tamanhos[0].id : null,
        adicionais: new Set(),
    };

    const acr = v => (Number(v) > 0 ? `<small>+ ${formatBRL(v)}</small>` : '');
    configPanel.innerHTML = `
        <button class="close" id="configClose">✕</button>
        <h2>${escHtml(product.name)}</h2>
        <p class="sub">${escHtml(product.desc || 'Monte do seu jeito.')}</p>

        <div class="cfg-section">
            <div class="cfg-label">1. Sabor <em>(escolha 1)</em></div>
            <div class="cfg-opts">
                ${op.sabores.map(x => `
                    <label class="cfg-opt"><input type="radio" name="cfgSabor" value="${x.id}"${x.id === _cfgCtx.saborId ? ' checked' : ''}><span>${escHtml(x.nome)}</span></label>`).join('')}
            </div>
        </div>

        <div class="cfg-section">
            <div class="cfg-label">2. Tamanho <em>(escolha 1)</em></div>
            <div class="cfg-opts">
                ${op.tamanhos.map(x => `
                    <label class="cfg-opt"><input type="radio" name="cfgTamanho" value="${x.id}"${x.id === _cfgCtx.tamanhoId ? ' checked' : ''}><span>${escHtml(x.nome)} ${acr(x.acrescimo)}</span></label>`).join('')}
            </div>
        </div>

        ${op.adicionais.length ? `
        <div class="cfg-section">
            <div class="cfg-label">3. Adicionais <em>(opcional)</em></div>
            <div class="cfg-opts">
                ${op.adicionais.map(x => `
                    <label class="cfg-opt"><input type="checkbox" name="cfgAdicional" value="${x.id}"><span>${escHtml(x.nome)} ${acr(x.preco)}</span></label>`).join('')}
            </div>
        </div>` : ''}

        <div class="cfg-summary"><span>Total</span><b id="cfgTotal"></b></div>
        <div class="cfg-error" id="cfgError"></div>
        <div class="confirm-actions">
            <button class="confirm-back" id="configCancel">Cancelar</button>
            <button class="confirm-final" id="configAdd" disabled>Adicionar ao pedido</button>
        </div>
    `;

    const atualizar = () => {
        document.getElementById('cfgTotal').textContent = formatBRL(calcPrecoConfig(product, _cfgCtx));
        const pronto = _cfgCtx.saborId !== null && _cfgCtx.tamanhoId !== null;
        document.getElementById('configAdd').disabled = !pronto;
        document.getElementById('cfgError').textContent =
            pronto ? '' : (_cfgCtx.saborId === null ? 'Escolha um sabor.' : 'Escolha um tamanho.');
    };

    configPanel.querySelectorAll('input[name="cfgSabor"]').forEach(el =>
        el.addEventListener('change', () => { _cfgCtx.saborId = Number(el.value); atualizar(); }));
    configPanel.querySelectorAll('input[name="cfgTamanho"]').forEach(el =>
        el.addEventListener('change', () => { _cfgCtx.tamanhoId = Number(el.value); atualizar(); }));
    configPanel.querySelectorAll('input[name="cfgAdicional"]').forEach(el =>
        el.addEventListener('change', () => {
            const id = Number(el.value);
            if (el.checked) _cfgCtx.adicionais.add(id); else _cfgCtx.adicionais.delete(id);
            atualizar();
        }));

    document.getElementById('configClose').addEventListener('click', closeConfigurator);
    document.getElementById('configCancel').addEventListener('click', closeConfigurator);
    document.getElementById('configAdd').addEventListener('click', () => {
        if (_cfgCtx.saborId === null || _cfgCtx.tamanhoId === null) return;
        addConfiguredToCart(_cfgCtx);
        const b = _cfgCtx.btn;
        closeConfigurator();
        if (b && document.body.contains(b)) {
            const original = b.textContent;
            b.textContent = '✓ Adicionado';
            b.classList.add('added');
            setTimeout(() => { b.textContent = original; b.classList.remove('added'); }, 1200);
        } else {
            openCart();   // veio do fluxo de login: mostra o carrinho
        }
    });

    atualizar();
    configOverlay.classList.add('open');
    document.body.style.overflow = 'hidden';
}

function closeConfigurator() {
    if (!configOverlay) return;
    configOverlay.classList.remove('open');
    _cfgCtx = null;
    document.body.style.overflow = overlay.classList.contains('open') ? 'hidden' : '';
}
configOverlay.addEventListener('click', (e) => { if (e.target === configOverlay) closeConfigurator(); });

function addConfiguredToCart(ctx) {
    const stall = STALLS.find(s => s.id === ctx.stallId);
    const product = stall && stall.products[ctx.idx];
    if (!product || !product.opcoes) return;
    const op = product.opcoes;
    const sabor = op.sabores.find(x => x.id === ctx.saborId);
    const tam = op.tamanhos.find(x => x.id === ctx.tamanhoId);
    const adds = op.adicionais.filter(x => ctx.adicionais.has(x.id));
    if (!sabor || !tam) return;

    const adicionaisIds = adds.map(a => a.id).sort((a, b) => a - b);
    // mesma combinação = mesma linha do carrinho (soma a quantidade)
    const key = `${ctx.stallId}__${ctx.idx}__c${sabor.id}-${tam.id}-${adicionaisIds.join('.')}`;
    const cart = getCart();
    const existing = cart.find(item => item.key === key);
    if (existing) {
        existing.qty += 1;
    } else {
        cart.push({
            key,
            stallId: ctx.stallId,
            stallName: stall.name,
            stallAddress: stall.address,
            productId: product.id || null,
            name: product.name,
            price: formatBRL(calcPrecoConfig(product, ctx)),   // preço unitário configurado
            img: product.img,
            qty: 1,
            config: { saborId: sabor.id, tamanhoId: tam.id, adicionaisIds },
            optionsLabel: [sabor.nome, tam.nome, ...adds.map(a => '+ ' + a.nome)].join(' · '),
        });
    }
    saveCart(cart);
}

function updateCartQty(key, delta) {
    let cart = getCart();
    const item = cart.find(i => i.key === key);
    if (!item) return;
    item.qty += delta;
    if (item.qty <= 0) cart = cart.filter(i => i.key !== key);
    saveCart(cart);
    renderCartPanel();
}
function cartTotal(cart) {
    return cart.reduce((sum, item) => sum + parsePrice(item.price) * item.qty, 0);
}
function updateCartBadge() {
    const cart = getCart();
    const count = cart.reduce((sum, i) => sum + i.qty, 0);
    const badge = document.getElementById('cartBadge');
    if (!badge) return;
    if (count > 0) {
        badge.style.display = 'flex';
        badge.textContent = count;
    } else {
        badge.style.display = 'none';
    }
}

const cartBtn = document.getElementById('cartBtn');
const cartOverlay = document.getElementById('cartOverlay');
const cartContent = document.getElementById('cartContent');

function openCart() {
    renderCartPanel();
    cartOverlay.classList.add('open');
    document.body.style.overflow = 'hidden';
}
function closeCart() {
    cartOverlay.classList.remove('open');
    document.body.style.overflow = '';
}
cartBtn.addEventListener('click', openCart);
document.getElementById('cartClose').addEventListener('click', closeCart);
cartOverlay.addEventListener('click', (e) => { if (e.target === cartOverlay) closeCart(); });

function renderCartPanel() {
    const cart = getCart();
    if (cart.length === 0) {
        cartContent.innerHTML = `<div class="cart-empty">Seu carrinho está vazio.<br>Adicione produtos das barraquinhas!</div>`;
        return;
    }
    const total = cartTotal(cart);
    const semVendedor = cart.filter(i => !i.vendorEmail);

    let aviso = '';
    if (semVendedor.length > 0) {
        aviso = `<div class="cart-warning">⚠️ ${semVendedor.length} item(ns) de barracas de exemplo não serão enviados ao servidor.</div>`;
    }

    cartContent.innerHTML = `
        ${aviso}
        ${cart.map(item => `
            <div class="cart-item">
                <img src="${item.img}" alt="${item.name}">
                <div class="info">
                    <div class="name">${item.name}</div>
                    ${item.optionsLabel ? `<div class="opts">${escHtml(item.optionsLabel)}</div>` : ''}
                    <div class="stall">${item.stallName}</div>
                    <div class="price">${item.price}</div>
                </div>
                <div class="qty-controls">
                    <button data-action="dec" data-key="${item.key}">−</button>
                    <span>${item.qty}</span>
                    <button data-action="inc" data-key="${item.key}">+</button>
                </div>
            </div>
        `).join('')}
        <div class="cart-total">
            <span>Total estimado</span>
            <span>${formatBRL(total)}</span>
        </div>
        <button class="cart-checkout" id="checkoutBtn">Revisar pedido</button>
    `;
    cartContent.querySelectorAll('[data-action="inc"]').forEach(btn => {
        btn.addEventListener('click', () => updateCartQty(btn.getAttribute('data-key'), 1));
    });
    cartContent.querySelectorAll('[data-action="dec"]').forEach(btn => {
        btn.addEventListener('click', () => updateCartQty(btn.getAttribute('data-key'), -1));
    });
    document.getElementById('checkoutBtn').addEventListener('click', openConfirm);
}

const confirmOverlay = document.getElementById('confirmOverlay');
const confirmPanel = document.getElementById('confirmPanel');

function groupCartByStall(cart) {
    const byStall = {};

    cart.forEach(item => {
        if (!byStall[item.stallId]) {
            byStall[item.stallId] = {
                stallId: item.stallId,
                name: item.stallName,
                address: item.stallAddress,
                items: []
            };
        }

        byStall[item.stallId].items.push(item);
    });

    return byStall;
}

function openConfirm() {
    const cart = getCart();
    if (cart.length === 0) return;

    const byStall = groupCartByStall(cart);
    const total = cartTotal(cart);

    confirmPanel.innerHTML = `
        <button class="close" id="confirmClose">✕</button>
        <h2>Confira sua reserva</h2>
        <p class="sub">Verifique os itens e as barraquinhas antes de confirmar.</p>
        ${Object.values(byStall).map(stall => `
            <div class="confirm-stall">
                <div class="stall-name">📍 ${stall.name}</div>
                ${stall.items.map(item => `
                    <div class="citem">
                        <span>${item.qty}x ${item.name}${item.optionsLabel ? `<small class="citem-opts">${escHtml(item.optionsLabel)}</small>` : ''}</span>
                        <span>${item.price}</span>
                    </div>
                `).join('')}
            </div>
        `).join('')}
        <div class="confirm-total">
            <span>Valor estimado dos itens</span>
            <span>${formatBRL(total)}</span>
        </div>
        <label class="confirm-check">
            <input type="checkbox" id="confirmCheck">
            <span>Confirmo que revisei os itens, as quantidades e as barraquinhas de retirada acima e desejo finalizar a reserva.</span>
        </label>
        <div class="confirm-actions">
            <button class="confirm-back" id="confirmBack">Voltar ao carrinho</button>
            <button class="confirm-final" id="confirmFinal" disabled>Confirmar reserva</button>
        </div>
    `;

    cartOverlay.classList.remove('open');
    confirmOverlay.classList.add('open');
    document.body.style.overflow = 'hidden';

    const checkbox = document.getElementById('confirmCheck');
    const finalBtn = document.getElementById('confirmFinal');
    checkbox.addEventListener('change', () => { finalBtn.disabled = !checkbox.checked; });

    document.getElementById('confirmClose').addEventListener('click', closeConfirm);
    document.getElementById('confirmBack').addEventListener('click', () => {
        closeConfirm();
        openCart();
    });
    finalBtn.addEventListener('click', () => {
        if (!checkbox.checked) return;
        finalizeOrder();
    });
}
function closeConfirm() {
    confirmOverlay.classList.remove('open');
    document.body.style.overflow = '';
}
confirmOverlay.addEventListener('click', (e) => { if (e.target === confirmOverlay) closeConfirm(); });

const ticketOverlay = document.getElementById('ticketOverlay');
const ticketPanel = document.getElementById('ticketPanel');

async function finalizeOrder() {
    const cart = getCart();
    if (cart.length === 0) return;

    const byStall = groupCartByStall(cart);
    const total = cartTotal(cart);

    const resultado = await enviarPedidosParaVendedores(byStall);

    if (!resultado || resultado.ok === false) {
        closeConfirm();
        return;
    }

    // A senha do pedido é a que o servidor gerou e gravou no banco —
    // é ela que aparece no ticket e depois em "Meus pedidos".
    const reservationId = resultado.reservaId || '—';

    ticketPanel.innerHTML = `
        <button class="close" id="ticketClose">✕</button>
        <div class="ticket-head">
            <span class="stamp">Reserva confirmada</span>
            <h2>Seu ticket de retirada</h2>
            <div class="order-code">Senha do pedido</div>
            <div class="order-id">${reservationId}</div>
        </div>
        ${Object.values(byStall).map(stall => `
            <div class="ticket-stall">
                <div class="stall-name">📍 ${stall.name}</div>
                <div class="stall-addr">${stall.address}</div>
                ${stall.items.map(item => `
                    <div class="titem">
                        <span>${item.qty}x ${item.name}${item.optionsLabel ? `<small class="citem-opts">${escHtml(item.optionsLabel)}</small>` : ''}</span>
                        <span>${item.price}</span>
                    </div>
                `).join('')}
            </div>
        `).join('')}
        <div class="ticket-foot">
            <span>Total estimado</span>
            <span>${formatBRL(total)}</span>
        </div>
        <div class="ticket-note">Mostre esta senha em cada barraquinha listada acima para retirar os itens reservados. Você também pode consultá-la a qualquer momento em "Meus pedidos". Bom passeio pela feira! 🧺</div>
    `;

    saveCart([]);
    closeConfirm();
    ticketOverlay.classList.add('open');
    document.getElementById('ticketClose').addEventListener('click', closeTicket);
}
function closeTicket() {
    ticketOverlay.classList.remove('open');
    document.body.style.overflow = '';
}
ticketOverlay.addEventListener('click', (e) => { if (e.target === ticketOverlay) closeTicket(); });

async function enviarPedidosParaVendedores(byStall) {
    const stalls = [];

    Object.values(byStall).forEach(stall => {
        if (!stall.stallId) {
            console.warn("[carrinho] item sem stallId, ignorado:", stall.name);
            return;
        }

        const valorNum = stall.items.reduce(
            (soma, item) => soma + parsePrice(item.price) * item.qty,
            0
        );

        stalls.push({
            stallId: stall.stallId,
            items: stall.items.map(i => ({
                id: i.productId || null,
                name: i.name,
                price: i.price,
                qty: i.qty,
                config: i.config || undefined   // só produtos configuráveis
            })),
            valor: formatBRL(valorNum),
            valorNumerico: valorNum
        });
    });

    if (!stalls.length) {
        console.warn("[carrinho] nenhum pedido para enviar.");
        return {
            ok: false,
            erro: "Nenhuma barraca válida encontrada"
        };
    }

    try {
        const r = await fetch("/api/orders", {
            method: "POST",
            headers: {
                "Content-Type": "application/json"
            },
            credentials: "include",
            body: JSON.stringify({ stalls })
        });

        const body = await r.json().catch(() => ({}));

        if (!r.ok) {
            console.error("[carrinho] servidor recusou:", r.status, body);

            const detalhes =
                Array.isArray(body.detalhes) && body.detalhes.length
                    ? "\n\n" + body.detalhes.join("\n")
                    : "";

            alert(
                "Não foi possível registrar o pedido. " +
                (body.erro || `HTTP ${r.status}`) +
                detalhes
            );

            return {
                ok: false,
                status: r.status,
                erro: body.erro
            };
        }

        console.log("[carrinho] pedidos enviados:", body);
        return body;

    } catch (e) {
        console.error("[carrinho] falha de rede:", e);
        alert("Falha de rede ao enviar o pedido. Tente novamente.");

        return {
            ok: false,
            erro: String(e)
        };
    }
}

let _cachedSession = null;
function readSession() { return _cachedSession; }
function clearSession() { _cachedSession = null; }

async function fetchSession() {
    try {
        const r = await fetch("/api/auth/session", { credentials: "include" });
        _cachedSession = await r.json();
    } catch (e) { _cachedSession = null; }
    return _cachedSession;
}

let pendingAction = null;

function showCatalog() {
    document.getElementById("loginScreen").classList.add("hidden");
    document.getElementById("loginNote").classList.remove("show");
    document.getElementById("app-cliente").style.display = "block";
    refreshVendorStalls().then(() => {
        renderFilters();
        renderGrid();
    });
}

function showLogin(reason) {
    document.getElementById("loginScreen").classList.remove("hidden");
    const note = document.getElementById("loginNote");
    if (reason === "checkout" || reason === "add-to-cart") {
        note.textContent = reason === "checkout"
            ? "Faça login (ou crie sua conta) pra finalizar a reserva."
            : "Faça login (ou crie sua conta) pra adicionar itens ao carrinho.";
        note.classList.add("show");
    } else {
        note.classList.remove("show");
    }
}

function requireLoginForOrder() {
    if (_cachedSession && _cachedSession.type === "cliente") return true;
    pendingAction = { type: "checkout" };
    if (cartOverlay) cartOverlay.classList.remove("open");
    showLogin("checkout");
    return false;
}

function requireLoginForCartAction(action) {
    if (_cachedSession && _cachedSession.type === "cliente") return true;
    pendingAction = action;
    showLogin("add-to-cart");
    return false;
}

function resumePendingAction() {
    if (!pendingAction) return;
    const action = pendingAction;
    pendingAction = null;
    if (!_cachedSession || _cachedSession.type !== "cliente") return;
    if (action.type === "checkout") {
        openConfirm();
    } else if (action.type === "add-to-cart") {
        addToCart(action.stallId, action.idx);
        openCart();
    } else if (action.type === "configure") {
        openConfigurator(action.stallId, action.idx);
    }
}

document.getElementById("openLoginBtn").addEventListener("click", () => showLogin());
document.getElementById("backToCatalogBtn").addEventListener("click", () => {
    pendingAction = null;
    showCatalog();
});

document.addEventListener("click", (e) => {
    const btn = e.target.closest("#checkoutBtn");
    if (!btn) return;
    if (!requireLoginForOrder()) {
        e.preventDefault();
        e.stopImmediatePropagation();
    }
}, true);

function injectLogoutControls(type, name) {
    updateAccountUI(true, type, name);
}

function updateAccountUI(loggedIn, type, name) {
    const loginBtn = document.getElementById("openLoginBtn");
    const cluster = document.getElementById("accountCluster");
    const logoutBtn = document.getElementById("logoutBtn");
    if (!loginBtn || !cluster) return;

    if (loggedIn && type === "cliente") {
        loginBtn.hidden = true;
        cluster.hidden = false;
        logoutBtn.textContent = "Sair (" + (name || "").split(" ")[0] + ")";
    } else {
        loginBtn.hidden = false;
        cluster.hidden = true;
    }
}

document.getElementById("logoutBtn").addEventListener("click", doLogout);

async function doLogout() {
    try { await fetch("/api/auth/logout", { method: "POST", credentials: "include" }); } catch (e) { }
    clearSession();
    updateAccountUI(false);
    document.getElementById("loginForm").reset();
    document.getElementById("registerForm").reset();
    showCatalog();
}

/* =====================================================================
   MEUS PEDIDOS — acompanhamento da senha e status de cada reserva
   ===================================================================== */
const ordersOverlay = document.getElementById("ordersOverlay");
const ordersContent = document.getElementById("ordersContent");

const STATUS_INFO = {
    pendente:  { label: "Aguardando confirmação", cls: "st-pendente" },
    preparo:   { label: "Em preparo",             cls: "st-preparo" },
    pronto:    { label: "Pronto pra retirar",      cls: "st-pronto" },
    concluido: { label: "Retirado",                cls: "st-concluido" },
    cancelado: { label: "Cancelado",               cls: "st-cancelado" },
};

async function openOrders() {
    ordersOverlay.classList.add("open");
    document.body.style.overflow = "hidden";
    ordersContent.innerHTML = `<p class="orders-empty">Carregando seus pedidos...</p>`;
    try {
        const r = await fetch("/api/orders/minhas", { credentials: "include" });
        if (!r.ok) throw new Error("HTTP " + r.status);
        const pedidos = await r.json();
        renderOrders(Array.isArray(pedidos) ? pedidos : []);
    } catch (e) {
        ordersContent.innerHTML = `<p class="orders-empty">Não foi possível carregar seus pedidos agora. Tente de novo em instantes.</p>`;
    }
}

function closeOrders() {
    ordersOverlay.classList.remove("open");
    document.body.style.overflow = "";
}

function renderOrders(pedidos) {
    if (!pedidos.length) {
        ordersContent.innerHTML = `<p class="orders-empty">Você ainda não fez nenhum pedido. Que tal dar uma volta pelo catálogo? 🧺</p>`;
        return;
    }
    ordersContent.innerHTML = pedidos.map(p => {
        const info = STATUS_INFO[p.status] || { label: p.status, cls: "st-pendente" };
        return `
        <div class="order-card">
            <div class="order-card-head">
                <div>
                    <div class="order-card-code">Senha: ${p.reserva_id || '—'}</div>
                    <div class="order-card-store">📍 ${p.loja_nome}</div>
                </div>
                <span class="order-status ${info.cls}">${info.label}</span>
            </div>
            <div class="order-card-items">${p.itens}</div>
            <div class="order-card-foot">
                <span>${p.valor}</span>
                <span>${p.hora}</span>
            </div>
        </div>
    `;
    }).join('');
}

document.getElementById("openOrdersBtn").addEventListener("click", openOrders);
document.getElementById("ordersClose").addEventListener("click", closeOrders);
ordersOverlay.addEventListener("click", (e) => { if (e.target === ordersOverlay) closeOrders(); });

async function enterApp(type, name, email, extra) {
    document.getElementById("loginScreen").classList.add("hidden");
    document.getElementById("loginNote").classList.remove("show");

    if (type === "vendedor") {
        window.location.href = "/parceiro.html";
        return;
    }
    if (type === "adm") {
        window.location.href = "/admin.html";
        return;
    }

    document.getElementById("app-cliente").style.display = "block";
    await refreshVendorStalls();
    renderFilters();
    renderGrid();
    injectLogoutControls(type, name);
    resumePendingAction();
}

const tabLoginBtn = document.getElementById("tabLoginBtn");
const tabRegisterBtn = document.getElementById("tabRegisterBtn");
const loginForm = document.getElementById("loginForm");
const registerForm = document.getElementById("registerForm");
const lpTitle = document.getElementById("lpTitle");
const lpSub = document.getElementById("lpSub");

tabLoginBtn.addEventListener("click", () => {
    tabLoginBtn.classList.add("active");
    tabRegisterBtn.classList.remove("active");
    loginForm.style.display = "block";
    registerForm.style.display = "none";
    lpTitle.textContent = "Entrar";
    lpSub.textContent = "Acesse com o mesmo login, cliente ou vendedor.";
});
tabRegisterBtn.addEventListener("click", () => {
    tabRegisterBtn.classList.add("active");
    tabLoginBtn.classList.remove("active");
    registerForm.style.display = "block";
    loginForm.style.display = "none";
    lpTitle.textContent = "Criar conta";
    lpSub.textContent = "Crie sua conta de cliente pra reservar produtos na feira.";
});

document.querySelectorAll(".toggle-eye").forEach(btn => {
    btn.addEventListener("click", () => {
        const target = document.getElementById(btn.dataset.target);
        const use = btn.querySelector("use");
        const showing = target.type === "password";
        target.type = showing ? "text" : "password";
        use.setAttribute("href", showing ? "#i-eye-off" : "#i-eye");
    });
});

document.getElementById("forgotBtn").addEventListener("click", () => {
    const msg = document.getElementById("forgotMsg");
    msg.classList.add("show");
    setTimeout(() => msg.classList.remove("show"), 4000);
});

loginForm.addEventListener("submit", async (e) => {
    e.preventDefault();
    const email = document.getElementById("loginEmail").value.trim().toLowerCase();
    const pass = document.getElementById("loginPass").value;
    const errorEl = document.getElementById("loginError");

    try {
        const r = await fetch("/api/auth/login", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            credentials: "include",
            body: JSON.stringify({ email, senha: pass }),
        });
        if (!r.ok) {
            errorEl.classList.add("show");
            return;
        }
        errorEl.classList.remove("show");
        _cachedSession = await r.json();
        enterApp(_cachedSession.type, _cachedSession.name, _cachedSession.email);
    } catch (err) {
        errorEl.classList.add("show");
    }
});

registerForm.addEventListener("submit", async (e) => {
    e.preventDefault();
    const nome = document.getElementById("regName").value.trim();
    const email = document.getElementById("regEmail").value.trim().toLowerCase();
    const senha = document.getElementById("regPass").value;
    const errorEl = document.getElementById("registerError");

    try {
        const r = await fetch("/api/auth/register", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            credentials: "include",
            body: JSON.stringify({ nome, email, senha }),
        });
        const body = await r.json();
        if (!r.ok) {
            errorEl.textContent = body.erro || "Erro ao cadastrar.";
            errorEl.classList.add("show");
            return;
        }
        errorEl.classList.remove("show");
        _cachedSession = body;
        enterApp("cliente", body.name, body.email);
    } catch (err) {
        errorEl.textContent = "Falha de rede.";
        errorEl.classList.add("show");
    }
});

(async function init() {
    updateCartBadge();
    await refreshVendorStalls();
    renderFilters();
    renderGrid();

    await fetchSession();
    if (_cachedSession && _cachedSession.type) {
        if (_cachedSession.type === "vendedor") {
            window.location.href = "/parceiro.html";
            return;
        }
        if (_cachedSession.type === "adm") {
            window.location.href = "/admin.html";
            return;
        }
        document.getElementById("loginScreen").classList.add("hidden");
        document.getElementById("loginNote").classList.remove("show");
        document.getElementById("app-cliente").style.display = "block";
        injectLogoutControls(_cachedSession.type, _cachedSession.name);
        resumePendingAction();
    } else {
        showCatalog();
    }
})();