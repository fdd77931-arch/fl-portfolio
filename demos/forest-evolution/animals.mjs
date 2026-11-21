const species = [
  ['ladybug', '瓢虫', 'Ladybug', '#edbaa3', '露水还挂在叶尖时，它已经沿着叶脉出发了。'],
  ['caterpillar', '毛毛虫', 'Caterpillar', '#cbd3a5', '慢慢地爬，认真地吃。一片叶子就是它的小世界。'],
  ['butterfly', '蝴蝶', 'Butterfly', '#f0d399', '展开琥珀色的翅膀，飞向第一朵阳光下的花。'],
  ['rabbit', '小兔子', 'Rabbit', '#edd9c8', '绒绒的长耳朵，总是先听见草丛里的动静。'],
  ['squirrel', '松鼠', 'Squirrel', '#e6bf9e', '它把橡果藏在树根旁，再用蓬松的尾巴盖住脚印。'],
  ['fox', '小狐狸', 'Fox', '#e8aa81', '黄昏时，它沿着苔藓小径轻轻地走。'],
  ['deer', '小鹿', 'Deer', '#e3c7a1', '斑点像落在背上的光，跟着它穿过林间空地。'],
  ['bear', '小熊', 'Bear', '#ccb195', '鼻尖先发现成熟的浆果，圆耳朵随后探出灌木。'],
  ['elephant', '大象', 'Elephant', '#c1cec7', '把长鼻子卷成问号，轻轻嗅过雨后的泥土。'],
  ['tiger', '老虎', 'Tiger', '#efc281', '它的条纹藏进摇晃的树影，脚步比风还轻。'],
  ['forest-king', '森林之王', 'Forest King', '#efcc83', '披着金棕色鬃毛，戴上由森林赠予的叶冠。'],
];

export const animals = species.map(([id, name, english, color, description], index) => ({
  id, name, english, color, description, level: index + 1,
  image: new URL(`./assets/animals/${id}.webp`, import.meta.url).href,
}));
