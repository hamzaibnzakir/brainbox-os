from __future__ import annotations
import argparse, json, wave
from pathlib import Path
import numpy as np
import torch
from openwakeword.utils import AudioFeatures
from openwakeword.train import Model

def read_wav(path: Path) -> np.ndarray:
    with wave.open(str(path), "rb") as w:
        sr, ch, width, n = w.getframerate(), w.getnchannels(), w.getsampwidth(), w.getnframes()
        raw = w.readframes(n)
    if width != 2 or sr != 16000:
        raise ValueError(f"{path}: expected 16-bit 16kHz WAV, got {sr}Hz/{width*8}bit")
    x = np.frombuffer(raw, dtype=np.int16).astype(np.float32) / 32768.0
    if ch > 1: x = x.reshape(-1, ch).mean(1)
    return x

def make_features(paths, F, length=32000):
    clips=[]
    for p in paths:
        x=read_wav(p)
        if len(x)<length: x=np.pad(x,(0,length-len(x)))
        else:
            start=max(0,(len(x)-length)//2); x=x[start:start+length]
        clips.append(x)
    return F.embed_clips(np.asarray([np.clip(c * 32768.0, -32768, 32767).astype(np.int16) for c in clips],dtype=np.int16), batch_size=32, ncpu=1)

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--positive",required=True); ap.add_argument("--negative",required=True)
    ap.add_argument("--out",required=True); ap.add_argument("--epochs",type=int,default=25)
    ap.add_argument("--layer-size",type=int,default=32)
    args=ap.parse_args()
    pos=sorted(Path(args.positive).glob("*.wav")); neg=sorted(Path(args.negative).glob("*.wav"))
    if not pos or not neg: raise SystemExit("Need positive and negative WAV files")
    F=AudioFeatures(device="cpu", ncpu=1)
    print(f"Embedding {len(pos)} positive + {len(neg)} negative clips",flush=True)
    Xp=make_features(pos,F); Xn=make_features(neg,F)
    X=np.concatenate([Xp,Xn]); y=np.concatenate([np.ones(len(Xp),dtype=np.float32),np.zeros(len(Xn),dtype=np.float32)])
    rng=np.random.default_rng(42); idx=rng.permutation(len(X)); X,y=X[idx],y[idx]
    split=max(1,int(len(X)*0.2)); Xv,yv=X[:split],y[:split]; Xt,yt=X[split:],y[split:]
    input_shape=X.shape[1:]
    trainer=Model(n_classes=1,input_shape=input_shape,model_type="dnn",layer_dim=args.layer_size)
    trainer.to("cpu")
    opt=torch.optim.AdamW(trainer.model.parameters(),lr=1e-3,weight_decay=1e-4)
    xb=torch.from_numpy(Xt); yb=torch.from_numpy(yt)[:,None]
    xv=torch.from_numpy(Xv); yv_t=torch.from_numpy(yv)[:,None]
    best=None; best_acc=-1
    for epoch in range(args.epochs):
        trainer.model.train(); perm=torch.randperm(len(xb)); losses=[]
        for start in range(0,len(xb),128):
            b=perm[start:start+128]; pred=trainer.model(xb[b]); loss=torch.nn.functional.binary_cross_entropy(pred,yb[b])
            opt.zero_grad(); loss.backward(); opt.step(); losses.append(float(loss))
        trainer.model.eval()
        with torch.no_grad():
            pv=trainer.model(xv); acc=float(((pv>=.5)==(yv_t>=.5)).float().mean())
            recall=float(((pv>=.5)&(yv_t==1)).sum()/max(1,(yv_t==1).sum()))
        print(f"epoch={epoch+1} loss={np.mean(losses):.4f} val_acc={acc:.3f} val_recall={recall:.3f}",flush=True)
        if acc>best_acc: best_acc=acc; best=trainer.model.state_dict()
    if best is not None: trainer.model.load_state_dict(best)
    out=Path(args.out); out.parent.mkdir(parents=True,exist_ok=True)
    torch.onnx.export(trainer.model.cpu(),torch.rand((1,*input_shape)),str(out),opset_version=13,input_names=["input"],output_names=["output"])
    meta={"phrase":"hey brainbox","positive_samples":len(pos),"negative_samples":len(neg),"validation_accuracy":best_acc,"input_shape":list(input_shape)}
    out.with_suffix(".json").write_text(json.dumps(meta,indent=2))
    print(json.dumps(meta),flush=True)

if __name__=="__main__": main()
