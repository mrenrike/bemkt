/**
 * BeContent — Camada de Analytics Centralizada
 * Gerencia GA4 (G-54MPDRQ62N) + Meta Pixel (319489982256904)
 *
 * Uso: bct('nome_do_evento', { parametros })
 *
 * Funil completo:
 *   Landing → Cadastro → Chat/Wizard → Geração → Preview → Planos → Compra
 */

;(function() {
  'use strict';

  var GA_ID    = 'G-54MPDRQ62N';
  var PIXEL_ID = '319489982256904';

  // ── Inicializa GA4 ──────────────────────────────────────────────
  window.dataLayer = window.dataLayer || [];
  function gtag(){ window.dataLayer.push(arguments); }
  window.gtag = gtag;

  var gaScript = document.createElement('script');
  gaScript.async = true;
  gaScript.src = 'https://www.googletagmanager.com/gtag/js?id=' + GA_ID;
  document.head.appendChild(gaScript);

  gtag('js', new Date());
  gtag('config', GA_ID, {
    send_page_view: true,
    page_title:     document.title,
    page_location:  window.location.href,
  });

  // ── Inicializa Meta Pixel ───────────────────────────────────────
  if (!window.fbq) {
    (function(f,b,e,v,n,t,s){
      if(f.fbq)return;n=f.fbq=function(){n.callMethod?
      n.callMethod.apply(n,arguments):n.queue.push(arguments)};
      if(!f._fbq)f._fbq=n;n.push=n;n.loaded=!0;n.version='2.0';
      n.queue=[];t=b.createElement(e);t.async=!0;t.src=v;
      s=b.getElementsByTagName(e)[0];s.parentNode.insertBefore(t,s);
    })(window,document,'script','https://connect.facebook.net/en_US/fbevents.js');
    fbq('init', PIXEL_ID);
  }
  fbq('track', 'PageView');

  // ── Mapa de eventos → GA4 + Meta Pixel ─────────────────────────
  var EVENT_MAP = {

    // Funil 1: Aquisição
    'cta_click': {
      ga: function(p){ gtag('event','generate_lead',{ event_category:'landing', event_label: p.label||'' }); },
      fb: function(p){ fbq('track','Lead', { content_name: p.label||'CTA' }); }
    },

    // Funil 2: Cadastro
    'sign_up': {
      ga: function(p){ gtag('event','sign_up',{ method:'email' }); },
      fb: function(p){ fbq('track','CompleteRegistration', { status: 'email' }); }
    },

    // Funil 3: Login
    'login': {
      ga: function(p){ gtag('event','login',{ method:'email' }); },
      fb: null
    },

    // Funil 4: Criação de carrossel
    'wizard_start': {
      ga: function(p){ gtag('event','wizard_start',{ event_category:'product' }); },
      fb: function(p){ fbq('trackCustom','WizardStart'); }
    },
    'wizard_step': {
      ga: function(p){ gtag('event','wizard_step',{ step: p.step||0, step_name: p.name||'' }); },
      fb: null
    },
    'carousel_start': {
      ga: function(p){ gtag('event','carousel_start',{ event_category:'product', template: p.template||'' }); },
      fb: function(p){ fbq('trackCustom','CarouselStart', { template: p.template||'' }); }
    },
    'carousel_complete': {
      ga: function(p){ gtag('event','carousel_complete',{ event_category:'product', template: p.template||'' }); },
      fb: function(p){ fbq('trackCustom','CarouselComplete', { template: p.template||'' }); }
    },

    // Funil 5: Planos
    'view_plans': {
      ga: function(p){
        gtag('event','view_item_list',{
          item_list_name: 'planos_becontent',
          items: [
            {item_id:'starter', item_name:'Starter', price:27, currency:'BRL'},
            {item_id:'pro',     item_name:'Pro',     price:47, currency:'BRL'},
            {item_id:'agency',  item_name:'Agency',  price:97, currency:'BRL'},
          ]
        });
      },
      fb: function(p){ fbq('track','ViewContent',{ content_name:'Planos BeContent', content_category:'plans' }); }
    },
    'select_plan': {
      ga: function(p){
        gtag('event','select_item',{
          item_list_name: 'planos_becontent',
          items:[{ item_id: p.plano||'', item_name: p.plano||'', price: p.valor||0, currency:'BRL' }]
        });
      },
      fb: function(p){ fbq('track','ViewContent',{ content_name: p.plano||'', value: p.valor||0, currency:'BRL' }); }
    },

    // Funil 6: Checkout
    'begin_checkout': {
      ga: function(p){
        gtag('event','begin_checkout',{
          currency:'BRL', value: p.valor||0,
          items:[{ item_id: p.plano||'', item_name: p.plano||'', price: p.valor||0, quantity:1 }]
        });
      },
      fb: function(p){ fbq('track','InitiateCheckout',{ value: p.valor||0, currency:'BRL', content_name: p.plano||'' }); }
    },

    // Funil 7: Compra confirmada
    'purchase': {
      ga: function(p){
        gtag('event','purchase',{
          transaction_id: p.transaction_id || String(Date.now()),
          currency:'BRL', value: p.valor||0,
          items:[{ item_id: p.plano||'', item_name: p.plano||'', price: p.valor||0, quantity:1 }]
        });
      },
      fb: function(p){ fbq('track','Purchase',{ value: p.valor||0, currency:'BRL', content_name: p.plano||'' }); }
    },
  };

  // ── API pública ─────────────────────────────────────────────────
  window.bct = function(eventName, params) {
    params = params || {};
    var def = EVENT_MAP[eventName];
    if (!def) {
      // Evento genérico — envia só para GA4
      gtag('event', eventName, params);
      return;
    }
    try { if (def.ga) def.ga(params); } catch(e){}
    try { if (def.fb && window.fbq) def.fb(params); } catch(e){}
  };

  // ── Rastreia cliques nos CTAs da landing automaticamente ────────
  document.addEventListener('DOMContentLoaded', function() {
    // CTAs da landing page com classe .cta-btn ou data-track
    document.querySelectorAll('[data-track]').forEach(function(el) {
      el.addEventListener('click', function() {
        bct('cta_click', { label: el.getAttribute('data-track') });
      });
    });

    // Planos: detecta se estamos na página de planos
    if (window.location.pathname.indexOf('planos') !== -1) {
      bct('view_plans');
    }

    // Detecta retorno do Mercado Pago com compra aprovada
    var urlParams = new URLSearchParams(window.location.search);
    var mpStatus  = urlParams.get('status') || urlParams.get('collection_status');
    if (mpStatus === 'approved') {
      var valor = parseFloat(urlParams.get('transaction_amount') || '0');
      var plano = urlParams.get('external_reference') || '';
      bct('purchase', { valor: valor, plano: plano, transaction_id: urlParams.get('payment_id') || '' });
      // Limpa URL sem recarregar
      window.history.replaceState({}, '', window.location.pathname);
    }
  });

})();
