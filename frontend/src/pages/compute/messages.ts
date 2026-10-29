import { defineMessages } from "../../i18n";
export const computeMessages = defineMessages({
  en: {
    localInvalidHelp: "Check the name and the identifier.",
    localMpiHelp: "MPI command, {ranks} being the number of processes. Example: mpirun -np {ranks}.",
    kind: "Execution environment", kinds: { wsl: "This computer · WSL", local: "This computer · Linux" },
    editor: "Profile configuration", save: "Save profile", cancel: "Close", name: "Name", id: "Identifier", idHelp: "Lower-case letters, digits and hyphens, 40 characters maximum. Cannot be changed once saved.",
    unsaved: "Unsaved changes", discardTitle: "Discard the profile changes?", discardText: "Changes to this profile have not been saved.", discard: "Discard and continue", invalid: "Check the profile fields", missing: "Still needed before the engine can be used",
    install: "Linux programs and folders", pathHelp: "Linux paths on the engine machine. A folder above the right one is accepted. The input data folder must be writable.",
    paths: { wrf_dir: "WRF folder", wps_dir: "WPS folder", geog_dir: "Geography folder · WPS_GEOG", input_dir: "Input data folder (GFS, ERA5)" },
    env: "Environment setup", envHelp: "Commands run before WPS and WRF (module load, source). Same environment as for compiling WRF.",
    mpi: "MPI command", mpiHelp: "{ranks} = number of processes. Examples: mpirun -np {ranks}, srun -n {ranks}.",
    connection: "Connection", distro: "WSL distribution", wslUser: "Linux user",
    notes: "Notes",
    verify: "Verify installation", verifyHelp: "Checks the engine paths, programs and libraries.", verifyTitle: "Installation checks", reachable: "Machine reached", unreachable: "Machine not reached", check: { ok: "OK", warn: "Warning", fail: "Failed" },
    verificationStale: "Profile changed: run the verification again."
  },
  fr: {
    localInvalidHelp: "Vérifiez le nom et l’identifiant.",
    localMpiHelp: "Commande MPI, {ranks} étant le nombre de processus. Exemple : mpirun -np {ranks}.",
    kind: "Environnement d'exécution", kinds: { wsl: "Cet ordinateur · WSL", local: "Cet ordinateur · Linux" },
    editor: "Configuration du profil", save: "Enregistrer le profil", cancel: "Fermer", name: "Nom", id: "Identifiant", idHelp: "Minuscules, chiffres et tirets, 40 caractères maximum. Non modifiable après enregistrement.",
    unsaved: "Modifications non enregistrées", discardTitle: "Abandonner les modifications du profil ?", discardText: "Les modifications de ce profil n'ont pas été enregistrées.", discard: "Abandonner et continuer", invalid: "Vérifiez les champs du profil", missing: "À compléter avant d'utiliser le moteur",
    install: "Programmes et dossiers Linux", pathHelp: "Chemins Linux sur la machine du moteur. Un dossier parent est accepté. Le dossier des données d'entrée doit être accessible en écriture.",
    paths: { wrf_dir: "Dossier WRF", wps_dir: "Dossier WPS", geog_dir: "Dossier géographique · WPS_GEOG", input_dir: "Dossier des données d'entrée (GFS, ERA5)" },
    env: "Configuration de l'environnement", envHelp: "Commandes lancées avant WPS et WRF (module load, source). Même environnement que pour la compilation de WRF.",
    mpi: "Commande MPI", mpiHelp: "{ranks} = nombre de processus. Exemples : mpirun -np {ranks}, srun -n {ranks}.",
    connection: "Connexion", distro: "Distribution WSL", wslUser: "Utilisateur Linux",
    notes: "Notes",
    verify: "Vérifier l'installation", verifyHelp: "Contrôle les chemins, les programmes et les bibliothèques du moteur.", verifyTitle: "Vérifications de l'installation", reachable: "Machine joignable", unreachable: "Machine non joignable", check: { ok: "OK", warn: "Avertissement", fail: "Échec" },
    verificationStale: "Profil modifié : relancer la vérification."
  },
});
