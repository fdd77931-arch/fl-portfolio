const steps = [
  { file: 'demo-start.png', name: '说明主诉', description: '用户先用自己的话描述主要症状。' },
  { file: 'demo-follow-up.png', name: '补充线索', description: '一次只处理一个问题，并说明提问原因。' },
  { file: 'demo-result.png', name: '查看行动结果', description: '结果页集中呈现行动建议、依据和升级信号。' },
];
const buttons = [...document.querySelectorAll('[data-step]')];
const screen = document.querySelector('#screen');
const caption = document.querySelector('#caption');
const next = document.querySelector('#next');
let current = 0;

function showStep(index) {
  current = index;
  const step = steps[index];
  screen.src = step.file;
  screen.alt = '循迹界面：' + step.name;
  caption.textContent = step.description;
  next.textContent = index === steps.length - 1 ? '重新查看 ↺' : '下一步 →';
  buttons.forEach((button, i) => {
    if (i === index) button.setAttribute('aria-current', 'step');
    else button.removeAttribute('aria-current');
  });
}
buttons.forEach((button, i) => button.addEventListener('click', () => showStep(i)));
next.addEventListener('click', () => showStep((current + 1) % steps.length));
