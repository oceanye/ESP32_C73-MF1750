/*
 * MF-1750 / M009F-T JLC EDA Pro helper.
 *
 * This version intentionally uses old JavaScript syntax so it can run in more
 * JLC/EasyEDA script runtimes. It is read-only by default.
 */

var AUTO_CREATE_TRACKS = false;
var AUTO_SELECT_NETS = true;

var criticalNets = [
  'CSB',
  'SL_CSB',
  'SI0',
  'SCL',
  'DC',
  'RST_N',
  'BUSY_N',
  'VDD',
  'VDDIO',
  '3V3',
  'GND',
  'VCP1',
  'CP2P',
  'CP2N',
  'VSL_LV2',
  'TSCL',
  'TSDA',
  'RESEC'
];

var repairPairs = [
  { net: 'VCP1', a: 'J1_44', b: 'C17_1', width: 0.254 },
  { net: 'CP2P', a: 'J1_43', b: 'C18_2', width: 0.254 },
  { net: 'CP2N', a: 'J1_42', b: 'C18_1', width: 0.254 },
  { net: 'VDDIO', a: 'J1_40', b: 'R7_2', width: 0.254 },
  { net: 'VDD', a: 'J1_38', b: 'R6_2', width: 0.254 },
  { net: 'CSB', a: 'J1_31', b: 'J2_5', width: 0.254 },
  { net: 'SI0', a: 'J1_33', b: 'J2_3', width: 0.254 },
  { net: 'TSCL', a: 'J1_24', b: 'R9_1', width: 0.254 },
  { net: 'TSDA', a: 'J1_25', b: 'R10_1', width: 0.254 },
  { net: 'VSL_LV2', a: 'J1_20', b: 'C12_1', width: 0.254 },
  { net: 'RESEC', a: 'J1_10', b: 'L2_2', width: 0.35 },
  { net: 'RESEC', a: 'L2_2', b: 'R3_1', width: 0.35 },
  { net: 'GND', a: 'J1_12', b: 'J1_21', width: 0.35 },
  { net: 'GND', a: 'J1_21', b: 'J1_39', width: 0.35 }
];

var reportLines = [];

function showToast(text) {
  try {
    if (typeof eda !== 'undefined' && eda.sys_ToastMessage && eda.sys_ToastMessage.showMessage) {
      if (typeof ESYS_ToastMessageType !== 'undefined' && ESYS_ToastMessageType.INFO !== undefined) {
        eda.sys_ToastMessage.showMessage(text, ESYS_ToastMessageType.INFO);
      } else {
        eda.sys_ToastMessage.showMessage(text);
      }
      return true;
    }
  } catch (e) {
  }
  return false;
}

function addLine(text) {
  reportLines.push(text);
  if (typeof console !== 'undefined' && console.log) {
    console.log('[MF1750] ' + text);
  }
}

function showReport() {
  var text = reportLines.join('\n');
  showToast('MF1750 script finished; check Console/log for details.');
  try {
    if (typeof eda !== 'undefined' && eda.sys_Dialog && eda.sys_Dialog.showInformationMessage) {
      eda.sys_Dialog.showInformationMessage(text, 'MF1750 Script Report', 'OK');
      return text;
    }
  } catch (e) {
  }
  if (typeof alert !== 'undefined') {
    alert(text);
  }
  return text;
}

function objectKeys(obj) {
  var result = [];
  if (!obj) return result;
  for (var key in obj) {
    result.push(key);
  }
  return result.sort();
}

function hasFunction(obj, name) {
  return !!(obj && typeof obj[name] === 'function');
}

function getObjectName(obj) {
  if (!obj) return '';
  var candidates = [
    obj.name,
    obj.pinName,
    obj.pin_name,
    obj.primitiveName,
    obj.primitive_name,
    obj.designator,
    obj.reference,
    obj.ref
  ];
  for (var i = 0; i < candidates.length; i++) {
    if (typeof candidates[i] === 'string' && candidates[i].length > 0) {
      return candidates[i];
    }
  }
  try {
    var text = JSON.stringify(obj);
    var match = text.match(/"(name|pinName|primitiveName|designator|reference|ref)"\s*:\s*"([^"]+)"/);
    if (match) return match[2];
  } catch (e) {
  }
  return '';
}

function getCenter(obj) {
  if (!obj) return null;
  var b = obj.bbox || obj.BBox || obj.boundingBox || obj.bounds;
  if (b) {
    var left = numberOrNull(b.left, b.x1, b.minX, b.startX);
    var right = numberOrNull(b.right, b.x2, b.maxX, b.endX);
    var top = numberOrNull(b.top, b.y1, b.minY, b.startY);
    var bottom = numberOrNull(b.bottom, b.y2, b.maxY, b.endY);
    if (left !== null && right !== null && top !== null && bottom !== null) {
      return { x: (left + right) / 2, y: (top + bottom) / 2 };
    }
  }
  var x = numberOrNull(obj.x, obj.X, obj.centerX, obj.pinX);
  var y = numberOrNull(obj.y, obj.Y, obj.centerY, obj.pinY);
  if (x !== null && y !== null) return { x: x, y: y };
  return null;
}

function numberOrNull() {
  for (var i = 0; i < arguments.length; i++) {
    if (typeof arguments[i] === 'number') return arguments[i];
  }
  return null;
}

function getNetPrimitives(net) {
  if (hasFunction(eda.pcb_Net, 'getAllPrimitivesByNet')) {
    return eda.pcb_Net.getAllPrimitivesByNet(net);
  }
  if (hasFunction(eda.pcb_Net, 'getPrimitivesByNet')) {
    return eda.pcb_Net.getPrimitivesByNet(net);
  }
  if (hasFunction(eda.pcb_Net, 'getNetPrimitives')) {
    return eda.pcb_Net.getNetPrimitives(net);
  }
  throw new Error('No known net primitive API found.');
}

function normalizeArray(value) {
  if (!value) return [];
  if (Object.prototype.toString.call(value) === '[object Array]') return value;
  if (typeof value.length === 'number') {
    var arr = [];
    for (var i = 0; i < value.length; i++) arr.push(value[i]);
    return arr;
  }
  return [value];
}

function inspectNets() {
  if (typeof eda === 'undefined') {
    addLine('ERROR: eda object is undefined. Please run inside PCB editor script window.');
    return;
  }

  addLine('Script started. AUTO_CREATE_TRACKS=' + AUTO_CREATE_TRACKS);
  addLine('eda keys: ' + objectKeys(eda).join(', '));
  addLine('eda.pcb_Net keys: ' + objectKeys(eda.pcb_Net).join(', '));

  for (var i = 0; i < criticalNets.length; i++) {
    var net = criticalNets[i];
    try {
      if (AUTO_SELECT_NETS && hasFunction(eda.pcb_Net, 'highlightNet')) {
        eda.pcb_Net.highlightNet(net);
      }
      var primitives = normalizeArray(getNetPrimitives(net));
      var names = [];
      for (var j = 0; j < primitives.length; j++) {
        var name = getObjectName(primitives[j]);
        if (name) names.push(name);
      }
      addLine('NET ' + net + ': primitives=' + primitives.length + ' names=' + names.slice(0, 20).join(', '));
    } catch (err) {
      addLine('NET ' + net + ': failed: ' + (err && err.message ? err.message : err));
    }
  }
}

function findPrimitiveByName(net, expectedName) {
  var primitives = normalizeArray(getNetPrimitives(net));
  var normalizedExpected = expectedName.toUpperCase();
  for (var i = 0; i < primitives.length; i++) {
    var name = getObjectName(primitives[i]).toUpperCase();
    if (name === normalizedExpected || name.indexOf(normalizedExpected) >= 0) {
      return primitives[i];
    }
  }
  return null;
}

function tryCreateRepairTracks() {
  if (!AUTO_CREATE_TRACKS) {
    addLine('AUTO_CREATE_TRACKS=false; no copper tracks were created.');
    return;
  }
  if (!eda.pcb_PrimitiveLine || !hasFunction(eda.pcb_PrimitiveLine, 'create')) {
    addLine('ERROR: eda.pcb_PrimitiveLine.create is unavailable.');
    return;
  }

  for (var i = 0; i < repairPairs.length; i++) {
    var pair = repairPairs[i];
    try {
      var a = findPrimitiveByName(pair.net, pair.a);
      var b = findPrimitiveByName(pair.net, pair.b);
      if (!a || !b) {
        addLine('SKIP missing pad: ' + pair.net + ' ' + pair.a + ' -> ' + pair.b);
        continue;
      }
      var ca = getCenter(a);
      var cb = getCenter(b);
      if (!ca || !cb) {
        addLine('SKIP missing coordinates: ' + pair.net + ' ' + pair.a + ' -> ' + pair.b);
        continue;
      }
      eda.pcb_PrimitiveLine.create(pair.net, 'TopLayer', ca.x, ca.y, cb.x, cb.y, pair.width, false);
      addLine('CREATED TopLayer line: ' + pair.net + ' ' + pair.a + ' -> ' + pair.b);
    } catch (err) {
      addLine('CREATE failed: ' + pair.net + ' ' + pair.a + ' -> ' + pair.b + ': ' + (err && err.message ? err.message : err));
    }
  }
}

try {
  showToast('MF1750 script started');
  inspectNets();
  tryCreateRepairTracks();
  addLine('Done. Run DRC after any manual or automatic track changes.');
  showReport();
} catch (err) {
  addLine('FATAL: ' + (err && err.message ? err.message : err));
  showReport();
}

reportLines.join('\n');
