const demo = document.querySelector('#demo-button');
const timer = document.querySelector('.timer');
const wave = document.querySelector('.wave');
let active = true;
demo.setAttribute('aria-pressed', 'true');

demo.addEventListener('click', () => {
  active = !active;
  timer.textContent = active ? '00:14' : '00:14 · PAUSED';
  demo.querySelector('.mic').textContent = active ? '●' : '▶';
  wave.style.opacity = active ? '1' : '.22';
  demo.setAttribute('aria-pressed', String(active));
});
