/* Couleurs d'identité (projets, personnes) : huit teintes choisies pour rester chaleureuses à côté du crème
   et du brun — terracotta, ambre, olive, sarcelle, bleu, prune, rose, rouille. Le même nom donne toujours
   la même couleur. */
export const HUES = [12, 36, 84, 168, 204, 268, 336, 24];
export const hue = (name) => HUES[[...String(name)].reduce((h, c) => (h * 31 + c.charCodeAt(0)) % 997, 7) % HUES.length];
