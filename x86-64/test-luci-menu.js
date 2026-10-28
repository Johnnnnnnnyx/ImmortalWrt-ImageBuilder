// Exercise the exact installed LuCI menu filter with the installed menu files.
const assert = require('node:assert/strict');
const { readFileSync, readdirSync } = require('node:fs');
const root = process.argv[2];
const source = readFileSync(`${root}/ui.js`, 'utf8');
const start = source.indexOf('function scrubMenu(node)');
const end = source.indexOf('const UIMenu=', start);
assert(start >= 0 && end > start, 'Adapt test to changed upstream menu implementation');
const scrubMenu = new Function('L', `${source.slice(start, end)}; return scrubMenu;`)(
    { isObject: value => value !== null && typeof value === 'object' && !Array.isArray(value) });
const tree = { satisfied: true };
for (const name of readdirSync(root).filter(name => name.endsWith('.json'))) {
    const entries = JSON.parse(readFileSync(`${root}/${name}`, 'utf8'));
    for (const [path, spec] of Object.entries(entries)) {
        let node = tree;
        for (const part of path.split('/')) {
            node.children ??= {};
            node = node.children[part] ??= { satisfied: true };
        }
        Object.assign(node, spec);
    }
}
const result = scrubMenu(structuredClone(tree)).children.admin.children;
assert.equal(result.vpn.satisfied, false, 'Empty VPN category must be hidden');
assert(!result.system.children?.['johnny-update'], 'Standalone updater must be absent');
const services = result.services.children;
assert(services.zerotier.satisfied);
assert(services.zerotier.order > services.meowx.order);
tree.children.admin.children.vpn.children = {
    other: { satisfied: true, title: 'Other VPN', action: { type: 'view', path: 'other' } }
};
assert(scrubMenu(tree).children.admin.children.vpn.satisfied, 'New VPN apps must become visible');
console.log('PASS: installed LuCI hides empty VPN, places ZeroTier under Services and retains future VPN entries');
