/* @ds-bundle: {"format":4,"namespace":"Forte","components":[{"name":"Button"},{"name":"StatusPill"},{"name":"Card"},{"name":"Paystub"}]} */
(function () {
  var React = window.React;
  var h = React.createElement;

  function cx() {
    return Array.prototype.filter.call(arguments, Boolean).join(' ');
  }

  function omit(props, keys) {
    var out = {};
    for (var k in props) {
      if (Object.prototype.hasOwnProperty.call(props, k) && keys.indexOf(k) === -1) out[k] = props[k];
    }
    return out;
  }

  // Money arrives in integer cents, the way the backend stores it.
  function money(cents) {
    var neg = cents < 0;
    var abs = Math.abs(Math.round(cents));
    var dollars = Math.floor(abs / 100);
    var rest = abs % 100;
    return (neg ? '-' : '') + '$' + dollars.toLocaleString('en-US') + '.' + (rest < 10 ? '0' : '') + rest;
  }

  function Button(props) {
    var variant = props.variant || 'secondary';
    var size = props.size || 'md';
    var rest = omit(props, ['variant', 'size', 'className', 'children']);
    return h(
      'button',
      Object.assign({ type: 'button' }, rest, {
        className: cx('ft-btn', 'ft-btn-' + variant, 'ft-btn-' + size, props.className)
      }),
      props.children
    );
  }

  function StatusPill(props) {
    return h(
      'span',
      {
        className: cx('ft-pill', props.current && 'ft-pill-current', props.className),
        'aria-current': props.current ? 'step' : undefined
      },
      props.children
    );
  }

  function Card(props) {
    var tone = props.tone || 'muted';
    return h(
      'section',
      { className: cx('ft-card', 'ft-card-' + tone, props.className) },
      props.eyebrow ? h('p', { className: 'ft-eyebrow' }, props.eyebrow) : null,
      props.title ? h('h3', { className: 'ft-card-title' }, props.title) : null,
      props.children ? h('div', { className: 'ft-card-body' }, props.children) : null
    );
  }

  function Paystub(props) {
    var lines = props.lines || [];
    var gross = props.grossCents || 0;
    var withheld = lines.reduce(function (sum, line) {
      return sum + (line.amountCents || 0);
    }, 0);
    return h(
      'article',
      { className: cx('ft-stub', props.className) },
      h(
        'header',
        { className: 'ft-stub-head' },
        h('p', { className: 'ft-eyebrow' }, props.label || 'Paystub'),
        props.period ? h('p', { className: 'ft-stub-period' }, props.period) : null
      ),
      h(
        'div',
        { className: 'ft-stub-row' },
        h('span', null, 'You earned'),
        h('span', { className: 'ft-num' }, money(gross))
      ),
      h(
        'div',
        { className: 'ft-stub-lines' },
        lines.map(function (line, i) {
          return h(
            'div',
            { key: i, className: 'ft-stub-row' },
            h(
              'span',
              { className: 'ft-stub-label' },
              h('span', null, line.label),
              line.note ? h('span', { className: 'ft-stub-note' }, line.note) : null
            ),
            h('span', { className: 'ft-num ft-stub-minus' }, money(-(line.amountCents || 0)))
          );
        })
      ),
      h(
        'div',
        { className: 'ft-stub-row ft-stub-total' },
        h('span', null, 'You take home'),
        h('span', { className: 'ft-num' }, money(gross - withheld))
      )
    );
  }

  window.Forte = Object.assign(window.Forte || {}, {
    Button: Button,
    StatusPill: StatusPill,
    Card: Card,
    Paystub: Paystub
  });
})();
