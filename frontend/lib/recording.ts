import { api, checksum, post, uploadFile } from './api';
type Clip = { key: string; session: string; sequence: number; blob: Blob; start_ms: number; end_ms: number; content_type: string };
function openDB(): Promise<IDBDatabase> { return new Promise((resolve,reject)=>{const req=indexedDB.open('talyn-pending-media',1);req.onupgradeneeded=()=>req.result.createObjectStore('clips',{keyPath:'key'});req.onsuccess=()=>resolve(req.result);req.onerror=()=>reject(req.error);}); }
async function persist(clip: Clip) { const db=await openDB();await new Promise<void>((resolve,reject)=>{const tx=db.transaction('clips','readwrite');tx.objectStore('clips').put(clip);tx.oncomplete=()=>resolve();tx.onerror=()=>reject(tx.error);});db.close(); }
async function remove(key:string) { const db=await openDB();await new Promise<void>((resolve,reject)=>{const tx=db.transaction('clips','readwrite');tx.objectStore('clips').delete(key);tx.oncomplete=()=>resolve();tx.onerror=()=>reject(tx.error);});db.close(); }
async function pending(session:string):Promise<Clip[]> { const db=await openDB();const rows=await new Promise<Clip[]>((resolve,reject)=>{const req=db.transaction('clips').objectStore('clips').getAll();req.onsuccess=()=>resolve(req.result);req.onerror=()=>reject(req.error);});db.close();return rows.filter(c=>c.session===session).sort((a,b)=>a.sequence-b.sequence); }
export function recordingType() { return ['video/webm;codecs=vp8,opus','video/webm;codecs=vp9,opus','video/mp4'].find(t=>MediaRecorder.isTypeSupported(t)); }
export class ClipRecorder {
  private recorder?: MediaRecorder;
  private timer?: ReturnType<typeof setTimeout>;
  private running=false;
  private uploads: Promise<void> = Promise.resolve();
  private finishClip: Promise<void> = Promise.resolve();
  private error: Error | null = null;
  sequence=0;
  constructor(private stream:MediaStream, private session:string, private startedAt:number, private onStatus:(s:string)=>void, private onError:(e:Error)=>void) {}
  async start() {
    const status=await api('/candidate/recordings/status',{},true);
    const saved=await pending(this.session);
    this.sequence=Math.max(status.next_sequence,...saved.map(c=>c.sequence+1),0);
    for(const clip of saved) await this.upload(clip);
    this.running=true;this.next();
  }
  private async upload(clip:Clip) {
    let last:unknown;
    for(let attempt=0;attempt<3;attempt++) {
      try {
        const result=await post('/candidate/recordings',{sequence:clip.sequence,sha256:await checksum(clip.blob),size:clip.blob.size,content_type:clip.content_type,start_ms:clip.start_ms,end_ms:clip.end_ms},true);
        if(!result.verified) {await uploadFile(result.upload,clip.blob);await post(`/candidate/recordings/${result.id}/complete`,undefined,true);}
        await remove(clip.key);this.onStatus(`Clip ${clip.sequence+1} uploaded`);return;
      }catch(e){last=e;await new Promise(r=>setTimeout(r,500*2**attempt));}
    }
    throw last;
  }
  private next() {
    if(!this.running)return;
    const type=recordingType();if(!type){this.onError(new Error('This browser cannot record supported video. Please request an accommodation.'));return;}
    const chunks:BlobPart[]=[];const start=Math.max(0,Date.now()-this.startedAt);const seq=this.sequence++;
    this.recorder=new MediaRecorder(this.stream,{mimeType:type,videoBitsPerSecond:450000,audioBitsPerSecond:48000});
    this.finishClip=new Promise<void>((resolve)=>{
      this.recorder!.ondataavailable=e=>{if(e.data.size)chunks.push(e.data);};
      this.recorder!.onstop=()=>{
        const end=Math.max(start+1,Date.now()-this.startedAt);const clip:Clip={key:`${this.session}:${seq}`,session:this.session,sequence:seq,blob:new Blob(chunks,{type}),start_ms:start,end_ms:end,content_type:type.split(';')[0]};
        void persist(clip).then(async()=>{
          const backlog=await pending(this.session);
          if(backlog.length>3){this.running=false;throw new Error('Uploads are delayed. Recording paused to limit local storage. Reconnect and resume.');}
          this.uploads=this.uploads.then(()=>this.upload(clip)).catch(e=>{this.error=e;this.running=false;this.onError(e);});
          this.next();
        }).catch(e=>{this.error=e;this.running=false;this.onError(e);}).finally(resolve);
      };
    });
    this.recorder.onerror=()=>{this.running=false;this.onError(new Error('Camera recording stopped. Check permissions and reconnect.'));};
    this.recorder.start();
    this.timer=setTimeout(()=>{if(this.recorder?.state==='recording')this.recorder.stop();},10000);
  }
  async stop() { this.running=false;clearTimeout(this.timer);if(this.recorder?.state==='recording')this.recorder.stop();await this.finishClip;await this.uploads;if(this.error)throw this.error;return this.sequence; }
  async finalize() {
    const expected=await this.stop();
    for(let attempt=0;attempt<12;attempt++) {
      const result=await post('/candidate/recordings/finalize-manifest',{expected_clips:expected},true);
      if(result.finalized)return result;
      this.onStatus('Verifying recording clips…');await new Promise(r=>setTimeout(r,1500));
    }
    throw new Error('Some clips are still verifying. Reopen the interview to retry finalization.');
  }
}
