// LuCI services are the boundary; exercise the actual component's DOM/actions.
const assert = require('node:assert/strict');
const { test } = require('node:test');
const { readFileSync } = require('node:fs');
const source = readFileSync(`${__dirname}/johnny-update.js`, 'utf8');

function setup(state = 'idle', readonly = false) {
    const nodes = [], calls = [], polls = [], modals = [];
    let response = { code: 0, stdout: JSON.stringify({ state, current: 'current', latest: 'latest', message: 'status' }) };
    function E(tag, attrs = {}, children = []) {
        const node = { tag, ...attrs, children, textContent: typeof children === 'string' ? children : '' };
        nodes.push(node);
        return node;
    }
    const ui = {
        createHandlerFn: (self, fn, ...args) => () => (typeof fn === 'string' ? self[fn] : fn).apply(self, args),
        showModal: (title, contents) => modals.push({ title, contents }),
        hideModal() {}, addNotification() {}, awaitReconnect: () => calls.push('reconnect')
    };
    const fs = { exec: async (_, [action]) => { calls.push(action); return response; } };
    const L = { hasViewPermission: () => !readonly, url: path => path };
    const component = new Function('baseclass', 'fs', 'ui', 'poll', 'E', 'L', 'window', source)(
        { extend: value => value }, fs, ui, {
            add: fn => polls.push(fn), remove: fn => polls.splice(polls.indexOf(fn), 1)
        }, E, L, { location: { host: 'router' } });
    return { component, calls, polls, modals, nodes, setResponse: value => { response = value; },
        button: label => nodes.find(n => n.tag === 'button' && n.textContent === label) };
}

for (const [state, disabled] of Object.entries({
    idle: [false, true, true], available: [false, false, true], ready: [false, true, false],
    checking: [true, true, true], downloading: [true, true, true], flashing: [true, true, true]
})) test(`update state ${state} enables only valid actions`, async () => {
    const t = setup(state);
    await t.component.render();
    assert.deepEqual(['检查更新', '下载并校验', '保留配置升级'].map(label => t.button(label).disabled), disabled);
});

test('read-only view cannot enable update actions', async () => {
    const t = setup('ready', true);
    await t.component.render();
    assert(t.nodes.filter(n => n.tag === 'button').every(n => n.disabled));
});

test('unavailable status leaves the surrounding firmware page renderable', async () => {
    const t = setup();
    t.setResponse({ code: 1, stderr: 'Permission denied' });
    const element = await t.component.render();
    assert.equal(element.tag, 'div');
    assert(t.nodes.some(n => n.textContent.includes('Permission denied')));
    assert(t.nodes.filter(n => n.tag === 'button').every(n => n.disabled));
});

test('poll failure disables previously available flashing', async () => {
    const t = setup('ready');
    await t.component.render();
    t.setResponse({ code: 0, stdout: 'not JSON' });
    await t.polls[0]();
    assert(t.button('保留配置升级').disabled);
});

test('flash requires a separate explicit confirmation', async () => {
    const t = setup('ready');
    await t.component.render();
    t.button('保留配置升级').click();
    assert.equal(t.modals.length, 1);
    assert(!t.calls.includes('flash'));
    await t.button('确认升级并重启').click();
    assert.deepEqual(t.calls, ['status', 'flash', 'reconnect']);
});

test('check and download use the fixed backend and do not flash', async () => {
    const t = setup('available');
    await t.component.render();
    await t.button('检查更新').click();
    await t.button('下载并校验').click();
    assert.deepEqual(t.calls, ['status', 'check', 'download']);
});

test('saving backup configuration and rerendering keeps only one poll', async () => {
    const t = setup();
    await t.component.render();
    await t.component.render();
    assert.equal(t.polls.length, 1);
});
