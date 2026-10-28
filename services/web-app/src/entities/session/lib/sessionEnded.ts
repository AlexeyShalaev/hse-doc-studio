// Сессия закончилась сама (истекла, отозвана), а не по явному выходу: форма входа
// объясняет это человеку. Флаг живёт в памяти вкладки и гаснет при следующем входе.

let ended = false;

export const markSessionEnded = (): void => {
  ended = true;
};

export const clearSessionEnded = (): void => {
  ended = false;
};

export const wasSessionEnded = (): boolean => ended;
