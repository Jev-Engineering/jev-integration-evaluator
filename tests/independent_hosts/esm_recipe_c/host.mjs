export const events = [];

export async function seam(request) { return await original(request); }

async function original(request) {
  events.push(['read', request.item]);
  globalThis.__jev_probe_effect?.('read', request.item);
  return 'read:' + request.item;
}

function hostRegistry(request) { return {read: original}; }
function hostGate(request, action) { return {allowed_actions: ['read'], baseline_permitted: true}; }
function hostValidate(request, action) { return request.permit === true && ['alpha', 'beta'].includes(request.item); }
function hostBlocked(request, reason) { return 'blocked'; }
function hostEvidence(request) { return {item: request.item}; }
function hostBaseline(request) { return 'read'; }
