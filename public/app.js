const $ = s => document.querySelector(s);
let config, removeReferral = false;
async function api(path, data) {
  const response = await fetch(path, data === undefined ? {} : {method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(data)});
  const result = await response.json(); if (!response.ok) throw new Error(result.error || 'Please try again.'); return result;
}
const params = new URLSearchParams(location.search);
const ready = Promise.all([api('/api/config'), api('/api/visit', {ref:params.get('ref') || '',source:params.get('utm_source') || params.get('src') || '',campaign:params.get('utm_campaign') || '',partner:params.get('partner') || ''})]).then(([c,v])=>{
  config=c; $('#schedule').textContent=c.schedule; $('#venue').textContent=c.venue; $('#fee').textContent=c.fee;
  if(v.referrer) { $('#referral-banner').hidden=false; $('#referral-name').textContent='Referred by '+v.referrer; }
  if(c.otp) { $('#otp-fields').hidden=false; $('#mobile-optional').textContent='(verified by SMS)'; $('#referral-form [name=phone]').required=true; $('#verification-note').textContent='Verify your mobile to create or recover your personal link.'; }
}).catch(error=>{ document.querySelectorAll('.form-message').forEach(el=>el.textContent='Connection problem. Refresh the page before submitting.'); throw error; });
ready.catch(()=>{});
$('#remove-referral').onclick=()=>{removeReferral=true; $('#referral-banner').hidden=true;};
async function submit(form, action) { const button=form.querySelector('button[type=submit]'),message=form.querySelector('.form-message'); button.disabled=true; message.textContent='Working on it…'; try { await ready; await action(); } catch(e) {message.textContent=e.message;} finally{button.disabled=false;} }
$('#booking-form').onsubmit=e=>{e.preventDefault(); const form=e.currentTarget;submit(form,async()=>{const data=Object.fromEntries(new FormData(form));data.consent=form.consent.checked;data.removeReferral=removeReferral;const result=await api('/api/bookings',data);form.replaceChildren();const mark=document.createElement('span');mark.className='success-mark';mark.textContent='✓';const title=document.createElement('h3');title.textContent=result.duplicate?'You’re already on our list.':'Thank you! We’ll be in touch.';const p=document.createElement('p');p.textContent=result.message;const id=document.createElement('p');id.className='notice';id.textContent=result.id?'Booking reference: '+result.id:'Please keep an eye out for our follow-up.';form.append(mark,title,p,id);});};
$('#send-code').onclick=async()=>{const button=$('#send-code'), form=$('#referral-form');button.disabled=true;try {await api('/api/otp/send',{phone:form.phone.value});form.querySelector('.form-message').textContent='Code sent. Check your SMS messages.';}catch(e){form.querySelector('.form-message').textContent=e.message;}finally{button.disabled=false;}};
$('#referral-form').onsubmit=e=>{e.preventDefault();const form=e.currentTarget;submit(form,async()=>{const data=Object.fromEntries(new FormData(form));data.consent=form.consent.checked;if(config.otp){const verified=await api('/api/otp/check',{phone:data.phone,code:data.code});data.token=verified.token;}const result=await api('/api/referrals',data);$('#share-url').value=result.url;$('#whatsapp-link').href='https://wa.me/?text='+encodeURIComponent('Join me in building financial confidence with Money Wise Women by myPAL. Explore the programme and request a seat: '+result.url);form.hidden=true;$('#referral-result').hidden=false;});};
$('#copy-link').onclick=async()=>{try{await navigator.clipboard.writeText($('#share-url').value);$('#copy-status').textContent='Link copied. Ready to share!';}catch(e){$('#share-url').select();$('#copy-status').textContent='Select and copy the link above.';}};
$('#another-link').onclick=()=>{$('#referral-result').hidden=true;$('#referral-form').hidden=false;$('#referral-form').reset();$('#referral-form .form-message').textContent='';};
if(location.pathname==='/refer') document.getElementById('refer').scrollIntoView();

let leadInView = false, leadSubmitted = false;
const mobileCTA = $('#mobile-cta');
function updateCTA() { mobileCTA.hidden = leadInView || leadSubmitted || /INPUT|SELECT|TEXTAREA/.test(document.activeElement.tagName); }
new IntersectionObserver(entries => { leadInView = entries[0].isIntersecting; updateCTA(); }, {threshold:0.1}).observe($('#book'));
document.addEventListener('focusin', updateCTA);
document.addEventListener('focusout', () => requestAnimationFrame(updateCTA));
new MutationObserver(() => { if (!$('#booking-form button[type=submit]')) { leadSubmitted = true; updateCTA(); } }).observe($('#booking-form'), {childList:true});
