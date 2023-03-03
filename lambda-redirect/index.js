'use strict';
var rules = require('./rules.js');

let rewriteRules;

const applyRules = function(e) {
  const req = e.Records[0].cf.request;
  var uri = req.uri;
  console.log(`Original URI: ${uri}`);
  // Linaro's link checker ensures that directories cannot
  // have full-stops in them, so if the URI doesn't end
  // with '/' *and* does not have a full-stop, it is an
  // unterminated URL, so add "/index.html".
  if (!uri.includes('.')) {
    var last = uri.substr(uri.length -1);
    if (last !== '/') {
      uri = uri + "/index.html";
    } else {
      uri = uri + "index.html";
    }
  }
  // Write the potentially modified URI back to the request
  req.uri = uri;

  console.log(`Processing ${uri}`);

  return rewriteRules.reduce((acc, rule) => {
    if (acc.skip == true) {
      return acc;
    }

    if (rule.host) {
      if (!rule.host.test(req.headers.host[0].value)) {
        return acc;
      }
    }

    if (rule.hostRW) {
      acc.res.headers.host[0].value = rule.hostRW;
    }

    var match = rule.regexp.test(req.uri);
    // If not match
    if (!match) {
      // Inverted rewrite
      if (rule.inverted) {
        acc.res.uri = rule.replace;
        acc.skip = rule.last;
        return acc;
      }
      return acc;
    }
    // Gone rules are no more - reused G for global replace
    // Gone
    // if (rule.gone) {
    //   return {'res': {status: '410',statusDescription: 'Gone'},'skip': rule.last};
    // }

    // Forbidden
    if (rule.forbidden) {
      return { 'res': { status: '403', statusDescription: 'Forbidden' }, 'skip': rule.last};
    }

    // Redirect
    if (rule.redirect) {
      return {
        'res': {
          status: rule.redirect || 301,
          statusDescription: 'Found',
          headers: {
            location: [{
              key: 'Location',
              value: uri.replace(rule.regexp, rule.replace),
            }],
          },
        }, 'skip': rule.last
      };
    }

    // Rewrite
    if (!rule.inverted) {
      if (rule.replace !== '-') {
        acc.res.uri = uri.replace(rule.regexp, rule.replace);
      }
      acc.skip = rule.last;
      return acc;
    }

  }, { 'res': Object.assign({},e.Records[0].cf.request)});
};
module.exports.applyRules = applyRules;


module.exports.handler = (e, ctx, cb) => {
  if (rewriteRules === undefined || process.env.IS_TEST) {
    rewriteRules = rules.parseRules(rules.loadRules());
  }
  cb(null,applyRules(e).res);
};
