const demo = document.querySelector('#demo-button');
const label = document.querySelector('.stage-top span:nth-child(2)');
const timer = document.querySelector('.timer');
let active = true;

demo.addEventListener('click', () => {
  active = !active;
  label.textContent = active ? 'VAANI IS LISTENING' : 'VAANI IS PAUSED';
  timer.textContent = active ? '00:14' : '00:14 · PAUSED';
  demo.querySelector('.mic').textContent = active ? '●' : '▶';
  document.querySelector('.wave').style.opacity = active ? '1' : '.22';
});
