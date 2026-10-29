/**
 * The equations of each wind analysis, as computed by the server (core/analysis, core/energy,
 * core/method/averaging.py), with a few words above each one.
 */
import type { EquationLine } from "../../../ui/Equation";

type Lang = "en" | "fr";
type Kind = "rose" | "production" | "curve" | "weibull" | "profile" | "grouped" | "stability" | "shear" | "veer" | "aggregate";

const words = {
  en: {
    mean10: "10-minute mean of the model time steps (tslist outputs)",
    speed: "Wind speed", direction: "Direction the wind comes from",
    frequency: "Frequency of sector s and speed class c",
    energy: "Energy of sector s: the 10-minute intervals i whose mean direction falls in s (mean power over the interval x 10 min)",
    loss: "Wake loss of sector s (E⁰: run without turbines)",
    fitch: "Power in WRF (Fitch): the cell's wind corrected for the slowing of its n turbines",
    induction: "Induction factor",
    bins: "Mean per 0.5 m/s bin i (IEC 61400-12-1 method of bins)",
    cp: "Power coefficient",
    share: "Share of time in speed class c, calms of 0 m/s in the first one", weibull: "Weibull curve: A close to the mean speed, k the narrower the spread the higher",
    profile: "Mean speed at each height z", alpha: "Exponent of the mean profile, between the lowest and highest heights",
    alphaEach: "Exponent at each time between the lowest and highest heights; the figure shown is their mean",
    group: "Mean of group g (hour of the day or month, UTC)",
    obukhov: "Obukhov length (RMOL = 1/L written by WRF, or from the surface fluxes)",
    classes: "Classes (Gryning et al. 2007)",
    veer: "Veer: upper minus lower direction, in (−180°, 180°]",
    hourly: "Hourly mean",
  },
  fr: {
    mean10: "Moyenne sur 10 minutes des pas de temps du modèle (sorties tslist)",
    speed: "Vitesse du vent", direction: "Direction d'où vient le vent",
    frequency: "Fréquence du secteur s et de la classe de vitesse c",
    energy: "Énergie du secteur s : les intervalles de 10 minutes i dont la direction moyenne tombe dans s (puissance moyenne de l'intervalle x 10 min)",
    loss: "Pertes de sillage du secteur s (E⁰ : calcul sans éoliennes)",
    fitch: "Puissance dans WRF (Fitch) : vent de la maille corrigé du ralentissement de ses n éoliennes",
    induction: "Facteur d'induction",
    bins: "Moyenne par classe i de 0,5 m/s (méthode des classes, IEC 61400-12-1)",
    cp: "Coefficient de puissance",
    share: "Part du temps dans la classe de vitesse c, calmes de 0 m/s dans la première", weibull: "Courbe de Weibull : A proche de la vitesse moyenne, k d'autant plus grand que les vitesses sont resserrées",
    profile: "Vitesse moyenne à chaque hauteur z", alpha: "Exposant du profil moyen, entre la hauteur la plus basse et la plus haute",
    alphaEach: "Exposant à chaque instant entre la hauteur la plus basse et la plus haute ; le chiffre affiché est leur moyenne",
    group: "Moyenne du groupe g (heure du jour ou mois, UTC)",
    obukhov: "Longueur d'Obukhov (RMOL = 1/L écrit par WRF, ou tirée des flux de surface)",
    classes: "Classes (Gryning et al. 2007)",
    veer: "Rotation : direction du haut moins direction du bas, dans ]−180°, 180°]",
    hourly: "Moyenne horaire",
  },
} as const;

/** The stability classes of a scheme of the server (core/analysis/stability.py), most unstable first. */
function classes(scheme: string, lang: Lang): [string, string][] {
  const fr = lang === "fr";
  if (scheme === "gryning2007-3") {
    return [
      [String.raw`-500 < L \le -50\ \mathrm{m}`, fr ? "instable" : "unstable"],
      [String.raw`|L| \ge 500\ \mathrm{m}`, fr ? "neutre" : "neutral"],
      [String.raw`10 \le L < 500\ \mathrm{m}`, "stable"],
    ];
  }
  const extended = scheme === "gryning2007-extended";
  return [
    [extended ? String.raw`-100 < L < 0\ \mathrm{m}` : String.raw`-100 < L \le -50\ \mathrm{m}`, fr ? "très instable" : "very unstable"],
    [String.raw`-200 < L \le -100\ \mathrm{m}`, fr ? "instable" : "unstable"],
    [String.raw`-500 < L \le -200\ \mathrm{m}`, fr ? "quasi neutre instable" : "near-neutral unstable"],
    [String.raw`|L| \ge 500\ \mathrm{m}`, fr ? "neutre" : "neutral"],
    [String.raw`200 \le L < 500\ \mathrm{m}`, fr ? "quasi neutre stable" : "near-neutral stable"],
    [String.raw`50 \le L < 200\ \mathrm{m}`, "stable"],
    [extended ? String.raw`0 < L < 50\ \mathrm{m}` : String.raw`10 \le L < 50\ \mathrm{m}`, fr ? "très stable" : "very stable"],
  ];
}

export function analysisEquations(kind: Kind, lang: Lang, scheme = "gryning2007"): EquationLine[] {
  const w = words[lang];
  const rho = lang === "fr" ? "1{,}23" : "1.23";
  const mean10 = { caption: w.mean10, tex: String.raw`\bar{U} = \frac{1}{T} \sum_{i} U_i \, \Delta t_i , \qquad T = 600\ \mathrm{s}` };
  const speed = { caption: w.speed, tex: String.raw`U = \sqrt{u^2 + v^2}` };
  const direction = { caption: w.direction, tex: String.raw`\bar{\theta} = \operatorname{atan2}\left( -\bar{u},\, -\bar{v} \right)` };
  switch (kind) {
    case "rose":
      return [mean10, direction, { caption: w.frequency, tex: String.raw`f_{s,c} = 100 \, \frac{N_{s,c}}{N}` }];
    case "production":
      return [
        { caption: w.energy, tex: String.raw`E_s = \sum_{i \,\in\, s} \bar{P}_i \times 10\ \mathrm{min}` },
        { caption: w.loss, tex: String.raw`L_s = 1 - \frac{E_s}{E^{0}_s}` },
        { caption: w.fitch, tex: String.raw`P = \tfrac{1}{2} \, \rho \, A \, U_*^{3} \, C_p(U_*) , \qquad U_* = \frac{U}{(1 - a)^{n}} , \qquad \rho = ${rho}\ \mathrm{kg/m^3}` },
        { caption: w.induction, tex: String.raw`a = \frac{1}{2} \left( 1 - \sqrt{1 - C_t} \right) \frac{A}{D \, \Delta x \, m}` },
      ];
    case "curve":
      return [
        { caption: w.bins, tex: String.raw`\bar{U}_i = \frac{1}{N_i} \sum_{j=1}^{N_i} U_{j} , \qquad \bar{P}_i = \frac{1}{N_i} \sum_{j=1}^{N_i} P_{j}` },
        { caption: w.cp, tex: String.raw`C_{p,i} = \frac{\bar{P}_i}{\tfrac{1}{2} \, \rho \, A \, \bar{U}_i^{\,3}} , \qquad A = \frac{\pi D^2}{4} , \qquad \rho = ${rho}\ \mathrm{kg/m^3}` },
      ];
    case "weibull":
      return [
        mean10,
        { caption: w.share, tex: String.raw`p_c = 100 \, \frac{N_c}{N}` },
        { caption: w.weibull, tex: String.raw`f(U) = \frac{k}{A} \left( \frac{U}{A} \right)^{k-1} e^{-\left( U / A \right)^{k}}` },
      ];
    case "profile":
      return [
        mean10,
        { caption: w.profile, tex: String.raw`\bar{U}(z) = \frac{1}{N} \sum_{i=1}^{N} U_i(z)` },
        { caption: w.alpha, tex: String.raw`\alpha = \frac{\ln\left( \bar{U}_2 / \bar{U}_1 \right)}{\ln\left( z_2 / z_1 \right)}` },
      ];
    case "grouped":
      return [mean10, { caption: w.group, tex: String.raw`\bar{U}_g = \frac{1}{N_g} \sum_{i \,\in\, g} U_i` }];
    case "stability":
      return [
        { caption: w.obukhov, tex: String.raw`L = - \frac{u_*^{3} \, \theta_v}{\kappa \, g \, \overline{w' \theta_v'}}` },
        {
          caption: w.classes,
          tex: String.raw`\begin{array}{rcl} ${classes(scheme, lang).map(([bounds, name]) => String.raw`${bounds} & \quad & \text{${name}}`).join(String.raw` \\ `)} \end{array}`,
        },
      ];
    case "shear":
      return [
        mean10,
        { caption: w.alphaEach, tex: String.raw`\alpha = \frac{\ln\left( U_2 / U_1 \right)}{\ln\left( z_2 / z_1 \right)}` },
      ];
    case "veer":
      return [mean10, direction, { caption: w.veer, tex: String.raw`\Delta\theta = \theta_2 - \theta_1` }];
    case "aggregate":
      return [mean10, speed, { caption: w.hourly, tex: String.raw`\bar{U}_h = \frac{1}{N_h} \sum_{i \,\in\, h} \bar{U}_i` }];
  }
}
