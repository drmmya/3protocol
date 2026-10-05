// VM contract for background-job rendering when the agent has no health sample.
const assert=require('assert'),fs=require('fs'),vm=require('vm');
const elements=new Map();
const document={getElementById(id){if(!elements.has(id))elements.set(id,{textContent:'',hidden:false,className:'',value:'',addEventListener(){},querySelector(){return {}},classList:{toggle(){},remove(){}}});return elements.get(id);},querySelectorAll(){return []},addEventListener(){}};
const c=vm.createContext({document,window:{addEventListener(){}},fetch:async()=>({status:401,ok:false,json:async()=>({error:'not signed in'})}),console,Date,Map,clearTimeout,setTimeout});
vm.runInContext(fs.readFileSync('panel/static/app.js','utf8'),c);
vm.runInContext("renderSnapshot({ready:false,sampled_at:null,error:'Agent unavailable',jobs:[{id:'j1',label:'Issue certificate',status:'failed',at:1,error:'ACME failed'}]})",c);
assert(elements.get('jobs')?.innerHTML?.includes('ACME failed'),'Job failure must remain visible without health data');
console.log('UI background-job outage contract passed');
