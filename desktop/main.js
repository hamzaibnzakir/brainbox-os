const { app, BrowserWindow, ipcMain, Tray, Menu, screen } = require('electron');
const gotSingleInstanceLock = app.requestSingleInstanceLock();
if (!gotSingleInstanceLock) { app.quit(); process.exit(0); }
const { spawn } = require('child_process');
const path = require('path');
let win, tray, brainboxProcess, quitting = false, lastState = 'sleeping';

function loadDotEnv(){
  const fs=require('fs');
  const file=path.join(__dirname,'..','.env');
  if(!fs.existsSync(file)) return;
  for(const raw of fs.readFileSync(file,'utf8').split(/\r?\n/)){
    const line=raw.trim();
    if(!line||line.startsWith('#')) continue;
    const i=line.indexOf('='); if(i<1) continue;
    const key=line.slice(0,i).trim(); let value=line.slice(i+1).trim();
    if((value.startsWith(')&&value.endsWith('))||(value.startsWith(")&&value.endsWith("))) value=value.slice(1,-1);
    if(!process.env[key]) process.env[key]=value;
  }
}
function pythonPath(){return process.platform==='win32'?path.join(__dirname,'..','.venv','Scripts','python.exe'):path.join(__dirname,'..','.venv','bin','python');}
function emit(event){if(win&&!win.isDestroyed())win.webContents.send('brainbox-event',event);}
function startBrainboxRuntime(){if(brainboxProcess&&!brainboxProcess.killed)return;brainboxProcess=spawn(pythonPath(),['-m','brainbox_os.cli','--voice'],{cwd:path.join(__dirname,'..'),windowsHide:true,stdio:['ignore','pipe','pipe'],env:{...process.env}});let buffer='';brainboxProcess.stdout.on('data',chunk=>{buffer+=chunk.toString();const lines=buffer.split(/\r?\n/);buffer=lines.pop()||'';for(const line of lines){try{const event=JSON.parse(line);if(event.event==='state')lastState=String(event.state||'').toLowerCase();emit(event)}catch(_){}}});brainboxProcess.stderr.on('data',chunk=>emit({event:'log',text:chunk.toString()}));brainboxProcess.on('error',e=>emit({event:'error',error:e.message}));brainboxProcess.on('exit',(code,signal)=>{brainboxProcess=null;if(!quitting){emit({event:'error',error:`Brainbox Core stopped (code ${code}, signal ${signal||'none'}). Restarting...`});setTimeout(startBrainboxRuntime,1500)}});}
function stopBrainboxRuntime(){if(brainboxProcess&&!brainboxProcess.killed)brainboxProcess.kill();brainboxProcess=null;}
function centerTop(w,h){const a=screen.getPrimaryDisplay().workArea;return{x:Math.round(a.x+(a.width-w)/2),y:a.y+12};}
function createWindow(){const p=centerTop(440,280);win=new BrowserWindow({width:440,height:280,x:p.x,y:p.y,frame:false,transparent:true,resizable:false,movable:false,alwaysOnTop:true,skipTaskbar:true,hasShadow:false,backgroundColor:'#00000000',webPreferences:{preload:path.join(__dirname,'preload.js'),contextIsolation:true,nodeIntegration:false}});win.setAlwaysOnTop(true,'floating');win.loadFile(path.join(__dirname,'index.html'));}
app.on('second-instance',()=>{if(win&&!win.isDestroyed()){if(win.isMinimized())win.restore();win.show();win.focus();}});
app.whenReady().then(()=>{loadDotEnv();createWindow();tray=new Tray(path.join(__dirname,'orb.png'));tray.setToolTip('Brainbox OS');tray.setContextMenu(Menu.buildFromTemplate([{label:'Show Brainbox',click:()=>win.show()},{label:'Restart Brainbox',click:()=>{stopBrainboxRuntime();startBrainboxRuntime()}},{type:'separator'},{label:'Quit Brainbox',click:()=>{quitting=true;app.quit()}}]));startBrainboxRuntime();});
ipcMain.handle('window-position',()=>win.getPosition());ipcMain.handle('runtime-state',()=>lastState);ipcMain.on('window-minimize',()=>{if(win&&!win.isDestroyed())win.hide()});ipcMain.on('quit-brainbox',()=>{quitting=true;app.quit()});
app.on('before-quit',()=>{quitting=true;stopBrainboxRuntime()});app.on('window-all-closed',e=>e.preventDefault());