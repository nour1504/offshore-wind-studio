"""The text of the exported bash scripts, French and English side by side: functions and
program of each script. The logic is the same in both languages (the end-to-end tests run
both); only comments, messages and names (variables, functions, folders) differ. The French
one follows the in-house reference scripts. Plain ASCII, tabs for indentation."""

# The closest folder holding a target: the same search as core/paths.py (BELOW levels), used by
# the exported scripts and on the engine machine (core/engine/commands.py)
FIND_BELOW = r"""## The folder that holds $2 (a relative path, for example main/wrf.exe): $1 itself or the closest
## of its subfolders (5 levels, hidden ones excepted), whatever their names; empty otherwise
find_below()
{
	local base=${1%/} target=$2 level found
	[ -e "$base/$target" ] && { echo "$base"; return 0; }
	[ -d "$base" ] || return 0
	for (( level = 1; level <= 5; level++ )); do
		found=$(find -L "$base" -mindepth "$level" -maxdepth "$level" -type d 2> /dev/null | LC_ALL=C sort \
			| while IFS= read -r folder; do
				case ${folder#"$base"} in */.*) continue ;; esac
				[ -e "$folder/$target" ] && { echo "$folder"; break; }
			done)
		[ -n "$found" ] && { echo "$found"; return 0; }
	done
}
"""

JOURNAL_FUNCTIONS = {
    "fr": r"""
## Message horodate dans le journal
journal()
{
	echo "[$(date -u '+%Y-%m-%d %H:%M:%S') UTC] $*"
}

## Arret propre : message, puis code de sortie non nul (le chainage Slurm s'arrete)
echec()
{
	journal "ERREUR : $*" >&2
	exit 1
}

## Le dossier qui contient $2 (chemin relatif, par exemple main/wrf.exe) : $1 lui-meme ou le plus
## proche de ses sous-dossiers (5 niveaux, caches exceptes), quels que soient leurs noms ; vide sinon
trouver_sous()
{
	local base=${1%/} cible=$2 niveau trouve
	[ -e "$base/$cible" ] && { echo "$base"; return 0; }
	[ -d "$base" ] || return 0
	for (( niveau = 1; niveau <= 5; niveau++ )); do
		trouve=$(find -L "$base" -mindepth "$niveau" -maxdepth "$niveau" -type d 2> /dev/null | LC_ALL=C sort \
			| while IFS= read -r dossier; do
				case ${dossier#"$base"} in */.*) continue ;; esac
				[ -e "$dossier/$cible" ] && { echo "$dossier"; break; }
			done)
		[ -n "$trouve" ] && { echo "$trouve"; return 0; }
	done
}

## Remplace le dossier de la variable $1 par celui qui contient vraiment $2 (trouver_sous) et le
## dit dans le journal ; arret si rien n'est trouve ($3 : ce qui est cherche)
resoudre_dossier()
{
	local nom=$1 cible=$2 quoi=$3 donne=${!1} trouve
	trouve=$(trouver_sous "$donne" "$cible")
	[ -n "$trouve" ] || echec "${quoi} introuvable dans ${donne} : corriger ${nom} en tete du script"
	[ "$trouve" = "${donne%/}" ] || journal "${nom} = ${trouve}"
	printf -v "$nom" '%s' "$trouve"
}
""",
    "en": r"""
## Time-stamped message in the log
log_line()
{
	echo "[$(date -u '+%Y-%m-%d %H:%M:%S') UTC] $*"
}

## Clean stop: message, then a non-zero exit code (the Slurm chain stops)
fail()
{
	log_line "ERROR: $*" >&2
	exit 1
}

"""
    + FIND_BELOW
    + r"""
## Replaces the folder of variable $1 by the one that really holds $2 (find_below) and says so in
## the log; stops when nothing is found ($3: what is looked for)
resolve_folder()
{
	local name=$1 target=$2 what=$3 given=${!1} found
	found=$(find_below "$given" "$target")
	[ -n "$found" ] || fail "${what} not found in ${given}: correct ${name} at the top of the script"
	[ "$found" = "${given%/}" ] || log_line "${name} = ${found}"
	printf -v "$name" '%s' "$found"
}
""",
}

NAMELIST_FUNCTIONS = {
    "fr": r"""
## Remplace la valeur d'une option de namelist par une seule ligne : option = valeur
## (les lignes de continuation de l'ancienne valeur sont retirees)
## $1 fichier, $2 option, $3 nouvelle valeur (texte de la namelist)
regler_option()
{
	local fichier=$1 option=$2 valeur=$3
	grep -qiE "^[[:space:]]*${option}[[:space:]]*=" "$fichier" \
		|| echec "option ${option} absente de ${fichier}"
	OPTION="$option" VALEUR="$valeur" awk '
	BEGIN { option = ENVIRON["OPTION"]; valeur = ENVIRON["VALEUR"]; cible = tolower(option) }
	suite && $0 !~ /=/ && $0 !~ /^[ \t]*[\/&]/ { next }
	{ suite = 0 }
	tolower($0) ~ ("^[ \t]*" cible "[ \t]*=") {
		marge = $0
		sub(/[^ \t].*$/, "", marge)
		print marge option " = " valeur
		suite = 1
		next
	}
	{ print }' "$fichier" > "${fichier}.tmp" && mv "${fichier}.tmp" "$fichier"
}

## La meme valeur pour chaque domaine : "v, v, v,"
par_domaine()
{
	local texte="" n
	for (( n = 1; n <= MAX_DOM; n++ )); do
		texte+="$1, "
	done
	echo "${texte%, },"
}

## Lie un executable ou un dossier sans remplacer un fichier du dossier courant
lier()
{
	local cible=$1 nom=${2:-$(basename "$1")}
	[ -e "$cible" ] || echec "introuvable : ${cible}"
	if [ -L "$nom" ] || [ ! -e "$nom" ]; then
		ln -sfn "$cible" "$nom"
	fi
}
""",
    "en": r"""
## Replaces the value of a namelist option by a single line: option = value
## (the continuation lines of the former value are removed)
## $1 file, $2 option, $3 new value (namelist text)
set_option()
{
	local file=$1 option=$2 value=$3
	grep -qiE "^[[:space:]]*${option}[[:space:]]*=" "$file" \
		|| fail "option ${option} missing from ${file}"
	OPTION="$option" VALUE="$value" awk '
	BEGIN { option = ENVIRON["OPTION"]; value = ENVIRON["VALUE"]; target = tolower(option) }
	continued && $0 !~ /=/ && $0 !~ /^[ \t]*[\/&]/ { next }
	{ continued = 0 }
	tolower($0) ~ ("^[ \t]*" target "[ \t]*=") {
		margin = $0
		sub(/[^ \t].*$/, "", margin)
		print margin option " = " value
		continued = 1
		next
	}
	{ print }' "$file" > "${file}.tmp" && mv "${file}.tmp" "$file"
}

## The same value for every domain: "v, v, v,"
per_domain()
{
	local text="" n
	for (( n = 1; n <= MAX_DOM; n++ )); do
		text+="$1, "
	done
	echo "${text%, },"
}

## Links an executable or a folder without replacing a file of the current folder
link_here()
{
	local target=$1 name=${2:-$(basename "$1")}
	[ -e "$target" ] || fail "not found: ${target}"
	if [ -L "$name" ] || [ ! -e "$name" ]; then
		ln -sfn "$target" "$name"
	fi
}
""",
}

WPS_FUNCTIONS = {
    "fr": r"""
## Dates de share pour tous les domaines
dates_wps()
{
	regler_option namelist.wps start_date "$(par_domaine "'$1'")"
	regler_option namelist.wps end_date "$(par_domaine "'$2'")"
}

## Liens GRIBFILE.AAA, GRIBFILE.AAB... vers les fichiers (comme link_grib.csh)
lier_grib()
{
	local lettres=ABCDEFGHIJKLMNOPQRSTUVWXYZ n=0 fichier
	rm -f GRIBFILE.???
	for fichier in "$@"; do
		ln -sf "$fichier" "GRIBFILE.${lettres:n/676%26:1}${lettres:n/26%26:1}${lettres:n%26:1}"
		(( n += 1 ))
	done
	(( n > 0 )) || return 1
	(( n <= 17576 )) || echec "trop de fichiers pour ungrib (${n})"
}

## Fichiers d'une source pour les annees d'un passage (motif avec %Y)
fichiers_source()
{
	local motif=$1 premiere=$2 derniere=$3 annee chemin dossier nom fichier
	declare -A vus=()
	for (( annee = premiere; annee <= derniere; annee++ )); do
		chemin=${motif//%Y/$annee}
		dossier=$(dirname "$chemin")
		nom=$(basename "$chemin")
		[ -d "$dossier" ] || continue
		# Le dossier et ses sous-dossiers (cachés exceptés), triés par nom de fichier
		while IFS= read -r -d '' fichier; do
			[ -n "${vus[$fichier]:-}" ] && continue
			vus[$fichier]=1
			echo "$fichier"
		done < <(find -L "$dossier" -mindepth 1 -maxdepth 9 -name '.?*' -prune -o -type f -iname "$nom" -printf '%f\t%p\0' 2> /dev/null | LC_ALL=C sort -z | cut -z -f2-)
	done
}

## Nombre d'instants des donnees entre deux dates (interval_seconds de namelist.wps)
instants_wps()
{
	local intervalle
	intervalle=$(awk -F'=' '/^ *interval_seconds/ {gsub(/[ ,]/, "", $2); print $2; exit}' namelist.wps)
	echo $(( ( $(date -u -d "${2/_/ }" +%s) - $(date -u -d "${1/_/ }" +%s) ) / ${intervalle:-21600} + 1 ))
}

## Place libre (octets) du disque d'un dossier
place_libre()
{
	echo $(( $(df -Pk "$1" | awk 'NR==2 {print $4}') * 1024 ))
}

## Avant ungrib : chaque instant donne un fichier intermediaire un peu plus gros que son GRIB,
## ecrit deux fois au plus fort (PFILE puis FILE). ungrib ne dit rien quand le disque est
## plein : la place est verifiee avant, et le resultat apres.
place_ungrib()
{
	local debut=$1 fin=$2 total=0 taille fichier instants besoin libre
	shift 2
	for fichier in "$@"; do
		taille=$(stat -L -c %s "$fichier" 2>/dev/null || echo 0)
		(( total += taille ))
	done
	instants=$(instants_wps "$debut" "$fin")
	besoin=$(( total / $# * 3 * instants ))
	libre=$(place_libre "$DOSSIER_UNGRIB")
	(( libre >= besoin )) || echec "pas assez de place pour ungrib dans $DOSSIER_UNGRIB : $(( libre / 1000000000 )) Go libres, environ $(( besoin / 1000000000 + 1 )) Go necessaires (${instants} instants). Liberez de la place ou raccourcissez la periode, puis relancez."
}

## Apres ungrib : un fichier par instant, et un disque qui n'a pas ete rempli
verifier_ungrib()
{
	local prefixe=$1 attendus=$2 trouves
	trouves=$(compgen -G "${prefixe}:*" | wc -l)
	(( $(place_libre "$DOSSIER_UNGRIB") >= 200000000 )) || echec "disque plein pendant ungrib : les fichiers ${prefixe}:* sont sans doute incomplets. Liberez de la place, supprimez-les, puis relancez."
	(( trouves >= attendus )) || echec "ungrib n'a ecrit que ${trouves} fichier(s) sur ${attendus} pour ${prefixe} (voir son journal) : des donnees manquent pour une partie de la periode."
}

## Lance un programme de WPS et controle son message de reussite
executer_wps()
{
	local nom=$1 lanceur=$2 sortie=$3
	journal "  > ${nom}.exe..."
	# shellcheck disable=SC2086
	$lanceur ./${nom}.exe > "$sortie" 2>&1
	grep -qs "Successful completion of ${nom}" "$sortie" "${nom}".log* \
		|| echec "${nom}.exe n'a pas termine correctement (voir ${sortie})"
}
""",
    "en": r"""
## share dates for every domain
wps_dates()
{
	set_option namelist.wps start_date "$(per_domain "'$1'")"
	set_option namelist.wps end_date "$(per_domain "'$2'")"
}

## Links GRIBFILE.AAA, GRIBFILE.AAB... to the files (as link_grib.csh does)
link_grib()
{
	local letters=ABCDEFGHIJKLMNOPQRSTUVWXYZ n=0 file
	rm -f GRIBFILE.???
	for file in "$@"; do
		ln -sf "$file" "GRIBFILE.${letters:n/676%26:1}${letters:n/26%26:1}${letters:n%26:1}"
		(( n += 1 ))
	done
	(( n > 0 )) || return 1
	(( n <= 17576 )) || fail "too many files for ungrib (${n})"
}

## Files of a source for the years of a pass (pattern with %Y)
source_files()
{
	local pattern=$1 first=$2 last=$3 year path folder name file
	declare -A seen=()
	for (( year = first; year <= last; year++ )); do
		path=${pattern//%Y/$year}
		folder=$(dirname "$path")
		name=$(basename "$path")
		[ -d "$folder" ] || continue
		# The folder and its subfolders (hidden ones excepted), sorted by file name
		while IFS= read -r -d '' file; do
			[ -n "${seen[$file]:-}" ] && continue
			seen[$file]=1
			echo "$file"
		done < <(find -L "$folder" -mindepth 1 -maxdepth 9 -name '.?*' -prune -o -type f -iname "$name" -printf '%f\t%p\0' 2> /dev/null | LC_ALL=C sort -z | cut -z -f2-)
	done
}

## Number of data times between two dates (interval_seconds of namelist.wps)
wps_times()
{
	local interval
	interval=$(awk -F'=' '/^ *interval_seconds/ {gsub(/[ ,]/, "", $2); print $2; exit}' namelist.wps)
	echo $(( ( $(date -u -d "${2/_/ }" +%s) - $(date -u -d "${1/_/ }" +%s) ) / ${interval:-21600} + 1 ))
}

## Free space (bytes) of the disk of a folder
free_space()
{
	echo $(( $(df -Pk "$1" | awk 'NR==2 {print $4}') * 1024 ))
}

## Before ungrib: each time gives an intermediate file a little larger than its GRIB, written
## twice at the peak (PFILE then FILE). ungrib says nothing when the disk is full: the space
## is checked before, and the result after.
ungrib_space()
{
	local start=$1 end=$2 total=0 size file times need free
	shift 2
	for file in "$@"; do
		size=$(stat -L -c %s "$file" 2>/dev/null || echo 0)
		(( total += size ))
	done
	times=$(wps_times "$start" "$end")
	need=$(( total / $# * 3 * times ))
	free=$(free_space "$UNGRIB_DIR")
	(( free >= need )) || fail "not enough space for ungrib in $UNGRIB_DIR: $(( free / 1000000000 )) GB free, about $(( need / 1000000000 + 1 )) GB needed (${times} times). Free some space or shorten the period, then run again."
}

## After ungrib: one file per time, and a disk that was not filled
check_ungrib()
{
	local prefix=$1 expected=$2 found
	found=$(compgen -G "${prefix}:*" | wc -l)
	(( $(free_space "$UNGRIB_DIR") >= 200000000 )) || fail "disk full during ungrib: the files ${prefix}:* are probably incomplete. Free some space, delete them, then run again."
	(( found >= expected )) || fail "ungrib wrote only ${found} file(s) out of ${expected} for ${prefix} (see its log): data are missing for part of the period."
}

## Runs a WPS program and checks its message of success
run_wps_program()
{
	local name=$1 launcher=$2 output=$3
	log_line "  > ${name}.exe..."
	# shellcheck disable=SC2086
	$launcher ./${name}.exe > "$output" 2>&1
	grep -qs "Successful completion of ${name}" "$output" "${name}".log* \
		|| fail "${name}.exe did not end correctly (see ${output})"
}
""",
}

WPS_PROGRAM = {
    "fr": r"""
set -u
debut_script=$(date -u '+%Y-%m-%d %H:%M:%S')
SECONDS=0

resoudre_dossier DOSSIER_WPS geogrid.exe "WPS (geogrid.exe)"
if (( FAIRE_GEOGRID )); then
	# La geographie de la resolution lue par geogrid (geog_data_res de namelist.wps) : la haute
	# des qu'un domaine la lit
	if awk -F= 'tolower($1) ~ /geog_data_res/ { print $2 }' namelist.wps | tr ',' '\n' | grep -vi lowres | grep -q '[[:alnum:]]'; then
		relief=topo_gmted2010_30s
	else
		relief=topo_gmted2010_5m
	fi
	resoudre_dossier DOSSIER_GEOG "${relief}/index" "La geographie (${relief})"
fi
for programme in geogrid.exe ungrib.exe metgrid.exe; do
	lier "$DOSSIER_WPS/$programme"
done
lier "$DOSSIER_WPS/geogrid" geogrid
lier "$DOSSIER_WPS/metgrid" metgrid
regler_option namelist.wps geog_data_path "'${DOSSIER_GEOG%/}/'"
regler_option namelist.wps opt_geogrid_tbl_path "'./geogrid/'"
regler_option namelist.wps opt_metgrid_tbl_path "'./metgrid/'"
regler_option namelist.wps opt_output_from_geogrid_path "'./'"
mkdir -p "$DOSSIER_UNGRIB" "$DOSSIER_MET_EM" journaux

## 1- geogrid, une seule fois
if (( FAIRE_GEOGRID )); then
	# geogrid met le chemin de la geographie et le dossier de chaque donnee dans 128
	# caracteres (modis_landuse_20class_30s_with_lakes/ en prend 37)
	geographie=${DOSSIER_GEOG%/}
	(( ${#geographie} <= 90 )) || echec "DOSSIER_GEOG trop long pour geogrid (${#geographie} caracteres, 90 au plus) : creer un lien court, par exemple ln -s \"$geographie\" ~/geog, et le mettre dans DOSSIER_GEOG"
	read -r _ debut fin _ <<< "${PASSAGES[0]}"
	dates_wps "$debut" "$fin"
	executer_wps geogrid "$LANCEUR_GEOGRID" journaux/geogrid.txt
fi

## 2- ungrib par source puis metgrid, annee par annee
for passage in "${PASSAGES[@]}"; do
	read -r annee debut fin debut_sst fin_sst <<< "$passage"
	journal "WPS pour l'annee ${annee} : ${debut} -> ${fin}"
	mkdir -p "$DOSSIER_UNGRIB/$annee"
	noms=()
	for source in "${SOURCES[@]}"; do
		if [[ " ${CONVERTIS[*]} " == *" ${source} "* ]]; then
			# Fichiers NetCDF convertis par le logiciel (SOURCE_AAAA-MM-JJ_HH) : relies sous
			# les noms d'ungrib (SOURCE:AAAA-MM-JJ_HH), lus par metgrid sans ungrib
			motif_variable="FICHIERS_${source}"
			compgen -G "${!motif_variable}/${source}_*" > /dev/null \
				|| echec "fichiers convertis absents pour ${source} (${!motif_variable})"
			for fichier in "${!motif_variable}/${source}"_*; do
				nom=$(basename "$fichier")
				ln -sf "$PWD/$fichier" "$DOSSIER_UNGRIB/$annee/${source}:${nom#"${source}"_}"
			done
			noms+=("'$DOSSIER_UNGRIB/$annee/$source'")
			continue
		fi
		if [[ " ${SOURCES_SST[*]} " == *" ${source} "* ]]; then
			# SST : periode elargie aux instants SST qui encadrent le passage
			premier=$debut_sst
			dernier=$fin_sst
		else
			premier=$debut
			dernier=$fin
		fi
		dates_wps "$premier" "$dernier"
		motif_variable="FICHIERS_${source}"
		mapfile -t fichiers < <(fichiers_source "${!motif_variable}" "${premier:0:4}" "${dernier:0:4}")
		lier_grib "${fichiers[@]}" || echec "aucun fichier pour ${source} (${!motif_variable})"
		place_ungrib "$premier" "$dernier" "${fichiers[@]}"
		table_variable="VTABLE_${source}"
		[ -f "${!table_variable}" ] || echec "${!table_variable} absente"
		ln -sf "${!table_variable}" Vtable
		regler_option namelist.wps prefix "'$DOSSIER_UNGRIB/$annee/$source'"
		rm -f "$DOSSIER_UNGRIB/$annee/$source":*
		executer_wps ungrib "$LANCEUR_UNGRIB" "journaux/ungrib_${source}_${annee}.txt"
		verifier_ungrib "$DOSSIER_UNGRIB/$annee/$source" "$(instants_wps "$premier" "$dernier")"
		rm -f GRIBFILE.???
		noms+=("'$DOSSIER_UNGRIB/$annee/$source'")
	done
	dates_wps "$debut" "$fin"
	liste=$(printf '%s, ' "${noms[@]}")
	regler_option namelist.wps fg_name "${liste%, },"
	regler_option namelist.wps opt_output_from_metgrid_path "'${DOSSIER_MET_EM%/}/'"
	executer_wps metgrid "$LANCEUR_METGRID" "journaux/metgrid_${annee}.txt"
done

journal "WPS termine. Debut : ${debut_script} UTC ; duree : $(( SECONDS / 3600 )) h $(( SECONDS % 3600 / 60 )) min"
exit 0
""",
    "en": r"""
set -u
script_start=$(date -u '+%Y-%m-%d %H:%M:%S')
SECONDS=0

resolve_folder WPS_DIR geogrid.exe "WPS (geogrid.exe)"
if (( RUN_GEOGRID )); then
	# The geography of the resolution geogrid reads (geog_data_res of namelist.wps): the high
	# one as soon as one domain reads it
	if awk -F= 'tolower($1) ~ /geog_data_res/ { print $2 }' namelist.wps | tr ',' '\n' | grep -vi lowres | grep -q '[[:alnum:]]'; then
		relief=topo_gmted2010_30s
	else
		relief=topo_gmted2010_5m
	fi
	resolve_folder GEOG_DIR "${relief}/index" "The geography (${relief})"
fi
for program in geogrid.exe ungrib.exe metgrid.exe; do
	link_here "$WPS_DIR/$program"
done
link_here "$WPS_DIR/geogrid" geogrid
link_here "$WPS_DIR/metgrid" metgrid
set_option namelist.wps geog_data_path "'${GEOG_DIR%/}/'"
set_option namelist.wps opt_geogrid_tbl_path "'./geogrid/'"
set_option namelist.wps opt_metgrid_tbl_path "'./metgrid/'"
set_option namelist.wps opt_output_from_geogrid_path "'./'"
mkdir -p "$UNGRIB_DIR" "$MET_EM_DIR" logs

## 1- geogrid, once
if (( RUN_GEOGRID )); then
	# geogrid joins the geography path and each dataset folder in 128 characters
	# (modis_landuse_20class_30s_with_lakes/ takes 37)
	geography=${GEOG_DIR%/}
	(( ${#geography} <= 90 )) || fail "GEOG_DIR too long for geogrid (${#geography} characters, 90 at most): make a short link, for example ln -s \"$geography\" ~/geog, and put it in GEOG_DIR"
	read -r _ start end _ <<< "${PASSES[0]}"
	wps_dates "$start" "$end"
	run_wps_program geogrid "$GEOGRID_LAUNCHER" logs/geogrid.txt
fi

## 2- ungrib for each source, then metgrid, year by year
for pass in "${PASSES[@]}"; do
	read -r year start end sst_start sst_end <<< "$pass"
	log_line "WPS for year ${year}: ${start} -> ${end}"
	mkdir -p "$UNGRIB_DIR/$year"
	names=()
	for source in "${SOURCES[@]}"; do
		if [[ " ${CONVERTED[*]} " == *" ${source} "* ]]; then
			# NetCDF files converted by the application (SOURCE_YYYY-MM-DD_HH): linked under
			# ungrib's names (SOURCE:YYYY-MM-DD_HH), read by metgrid without ungrib
			pattern_variable="FILES_${source}"
			compgen -G "${!pattern_variable}/${source}_*" > /dev/null \
				|| fail "converted files missing for ${source} (${!pattern_variable})"
			for file in "${!pattern_variable}/${source}"_*; do
				name=$(basename "$file")
				ln -sf "$PWD/$file" "$UNGRIB_DIR/$year/${source}:${name#"${source}"_}"
			done
			names+=("'$UNGRIB_DIR/$year/$source'")
			continue
		fi
		if [[ " ${SOURCES_SST[*]} " == *" ${source} "* ]]; then
			# SST: period widened to the SST times around the pass
			first=$sst_start
			last=$sst_end
		else
			first=$start
			last=$end
		fi
		wps_dates "$first" "$last"
		pattern_variable="FILES_${source}"
		mapfile -t files < <(source_files "${!pattern_variable}" "${first:0:4}" "${last:0:4}")
		link_grib "${files[@]}" || fail "no file for ${source} (${!pattern_variable})"
		ungrib_space "$first" "$last" "${files[@]}"
		table_variable="VTABLE_${source}"
		[ -f "${!table_variable}" ] || fail "${!table_variable} missing"
		ln -sf "${!table_variable}" Vtable
		set_option namelist.wps prefix "'$UNGRIB_DIR/$year/$source'"
		rm -f "$UNGRIB_DIR/$year/$source":*
		run_wps_program ungrib "$UNGRIB_LAUNCHER" "logs/ungrib_${source}_${year}.txt"
		check_ungrib "$UNGRIB_DIR/$year/$source" "$(wps_times "$first" "$last")"
		rm -f GRIBFILE.???
		names+=("'$UNGRIB_DIR/$year/$source'")
	done
	wps_dates "$start" "$end"
	list=$(printf '%s, ' "${names[@]}")
	set_option namelist.wps fg_name "${list%, },"
	set_option namelist.wps opt_output_from_metgrid_path "'${MET_EM_DIR%/}/'"
	run_wps_program metgrid "$METGRID_LAUNCHER" "logs/metgrid_${year}.txt"
done

log_line "WPS done. Start: ${script_start} UTC; duration: $(( SECONDS / 3600 )) h $(( SECONDS % 3600 / 60 )) min"
exit 0
""",
}

WRF_FUNCTIONS = {
    "fr": r"""
## Dates de time_control pour une fenetre : $1 debut, $2 fin, $3 duree (s), $4 reprise (1 :
## depart du wrfrst de la fenetre precedente). run_* et end_* concordent : WRF donne la
## priorite a run_*. En continu, un wrfrst est ecrit a la fin de chaque fenetre.
dates_wrf()
{
	local debut=$1 fin=$2 duree=$3 reprise=$4 quand date
	for quand in start end; do
		if [ "$quand" = start ]; then date=$debut; else date=$fin; fi
		regler_option namelist.input "${quand}_year" "$(par_domaine "${date:0:4}")"
		regler_option namelist.input "${quand}_month" "$(par_domaine "$((10#${date:5:2}))")"
		regler_option namelist.input "${quand}_day" "$(par_domaine "$((10#${date:8:2}))")"
		regler_option namelist.input "${quand}_hour" "$(par_domaine "$((10#${date:11:2}))")"
		regler_option namelist.input "${quand}_minute" "$(par_domaine "$((10#${date:14:2}))")"
		regler_option namelist.input "${quand}_second" "$(par_domaine "$((10#${date:17:2}))")"
	done
	regler_option namelist.input run_days "0,"
	regler_option namelist.input run_hours "$(( duree / 3600 )),"
	regler_option namelist.input run_minutes "$(( duree % 3600 / 60 )),"
	regler_option namelist.input run_seconds "$(( duree % 60 )),"
	if (( reprise )); then
		regler_option namelist.input restart ".true.,"
	else
		regler_option namelist.input restart ".false.,"
	fi
	(( CONTINU == 0 )) || regler_option namelist.input restart_interval "$(( duree / 60 )),"
}

## Lance real.exe ou wrf.exe et controle SUCCESS COMPLETE
executer_wrf()
{
	local programme=$1 attendu=$2 sortie=$3
	rm -f rsl.out.* rsl.error.*
	journal "  > ${programme}..."
	# shellcheck disable=SC2086
	$LANCEUR "./${programme}" > "$sortie" 2>&1
	local retour=$?
	if [ -f rsl.error.0000 ]; then
		cp rsl.error.0000 "${sortie%.txt}.rsl.txt"
		grep -q "$attendu" rsl.error.0000 \
			|| echec "${programme} : pas de '${attendu}' dans rsl.error.0000 (voir ${sortie%.txt}.rsl.txt)"
	else
		grep -q "$attendu" "$sortie" || echec "${programme} : pas de '${attendu}' (voir ${sortie})"
	fi
	(( retour == 0 )) || journal "  ${programme} a rendu le code ${retour} malgre SUCCESS COMPLETE"
}

## Nombre de niveaux de metgrid, lus dans le premier met_em du domaine 1
niveaux_metgrid()
{
	local premier niveaux sol
	if [ -n "$NIVEAUX_METGRID" ]; then
		regler_option namelist.input num_metgrid_levels "${NIVEAUX_METGRID},"
		return
	fi
	premier=$(find . -maxdepth 1 -name 'met_em.d01.*' | sort | head -n 1)
	[ -n "$premier" ] || echec "aucun met_em.d01 dans ${DOSSIER_MET_EM}"
	command -v ncdump > /dev/null \
		|| echec "ncdump introuvable : renseignez NIVEAUX_METGRID dans les parametres de base"
	niveaux=$(ncdump -h "$premier" | sed -n -E 's/^[[:space:]]*num_metgrid_levels = ([0-9]+) ;/\1/p')
	sol=$(ncdump -h "$premier" | sed -n -E 's/^[[:space:]]*:NUM_METGRID_SOIL_LEVELS = ([0-9]+) ;/\1/p')
	[ -n "$niveaux" ] && [ -n "$sol" ] || echec "niveaux illisibles dans ${premier}"
	regler_option namelist.input num_metgrid_levels "${niveaux},"
	regler_option namelist.input num_metgrid_soil_levels "${sol},"
}

## Decoupe une serie tslist d'une fenetre : garde ]debut utile, fin utile], le temps devient
## des heures depuis D, l'en-tete prend la date D. Pas fixe : par numero de pas, avec controle
## des nombres de lignes ; pas adaptatif : par le temps. Apres une reprise (pas de mise en
## route), le temps compte depuis le debut de la fenetre ou depuis le tout premier depart :
## les deux sont reconnus.
## $1 fichier brut, $2 colonne du temps, $3 domaine (1, 2...), $4 dernier pas garde,
## $5 decalage (s), $6 duree simulee (s), $7 fichier produit, $8 reprise (1 : depart d'un wrfrst),
## $9 mise en route de la fenetre (s ; 0 apres une reprise)
decouper_serie()
{
	local brut=$1 colonne=$2 domaine=$3 dernier=$4 decalage=$5 duree=$6 produit=$7 reprise=$8
	local mise_en_route=$9
	local num=${PAS_NUM[domaine-1]} den=${PAS_DEN[domaine-1]}
	# Premier pas garde : plancher(mise en route / dt) + 1
	local premier=$(( mise_en_route * den / num + 1 ))
	awk -v col="$colonne" -v num="$num" -v den="$den" -v n0="$premier" -v n1="$dernier" \
		-v off="$decalage" -v spin="$mise_en_route" -v duree="$duree" \
		-v reprise="$reprise" -v base="$(( decalage + MISE_EN_ROUTE_S ))" \
		-v adaptatif="$PAS_ADAPTATIF" -v date_d="$DEBUT_ETUDE" '
	NR == 1 {
		entete = $0
		sub(/[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9]_[0-9][0-9]:[0-9][0-9]:[0-9][0-9][ \t]*$/, date_d, entete)
		print entete
		next
	}
	NF == 0 { next }
	{
		t = $col * 3600
		if (reprise == 1 && lues++ == 0 && t > base / 2) { cumul = 1 }
		if (cumul) { t -= base }
		if (adaptatif == 1) {
			if (t <= spin + 0.5) { retirees++; next }
			if (t > duree + 0.5) { apres++; next }
			if (gardees > 0 && t <= precedent) { erreur = "temps non croissant ligne " NR }
			precedent = t
			$col = sprintf("%.6f", (off + t) / 3600)
		} else {
			n = int(t * den / num + 0.5)
			if (n < n0) { retirees++; next }
			if (n > n1) { apres++; next }
			if (gardees > 0 && n != attendu) { erreur = "pas manquant ou double ligne " NR }
			if (gardees == 0 && n != n0) { erreur = "premier pas " n " au lieu de " n0 }
			attendu = n + 1
			$col = sprintf("%.6f", (off + n * num / den) / 3600)
		}
		gardees++
		print
	}
	END {
		if (adaptatif != 1) {
			if (retirees != n0 - 1) { erreur = erreur " ; " retirees+0 " lignes de mise en route au lieu de " n0 - 1 }
			if (gardees != n1 - n0 + 1) { erreur = erreur " ; " gardees+0 " lignes gardees au lieu de " n1 - n0 + 1 }
		}
		if (erreur != "") { print erreur > "/dev/stderr"; exit 3 }
	}' "$brut" > "${produit}.tmp" || return 1
	mv "${produit}.tmp" "$produit"
}

## Sauvegarde et decoupe les tslist d'une fenetre, juste apres wrf.exe
## $1 id, $2 decalage (s), $3 duree simulee (s), $4 reprise, $5 mise en route (s),
## $6... dernier pas de chaque domaine
sauver_tslist()
{
	local id=$1 decalage=$2 duree=$3 reprise=$4 mise_en_route=$5
	shift 5
	local derniers=("$@") nom domaine variable brut colonne compte=0
	mkdir -p tslist_fenetres
	for nom in "${TSNAME[@]}"; do
		for (( domaine = 1; domaine <= MAX_DOM; domaine++ )); do
			for variable in "${TSVARS[@]}"; do
				brut="${nom}.d$(printf '%02d' "$domaine").${variable}"
				[ -f "$brut" ] || continue
				if [ "$variable" = TS ]; then colonne=2; else colonne=1; fi
				decouper_serie "$brut" "$colonne" "$domaine" "${derniers[domaine-1]}" \
					"$decalage" "$duree" "tslist_fenetres/${brut}.${id}" "$reprise" "$mise_en_route" \
					|| echec "decoupe de ${brut} (fenetre ${id})"
				rm -f "$brut"
				(( compte += 1 ))
			done
		done
	done
	journal "  > ${compte} series tslist decoupees"
}

## Continu : vrai si le wrfrst_d01 de l'instant $1 (fin de la fenetre precedente) est la
restart_present()
{
	local fichier
	for fichier in wrfrst_d01_*; do
		[ -e "$fichier" ] || continue
		[ "$(instant_wrfout "$fichier")" = "$1" ] && return 0
	done
	return 1
}

## Continu : garde seulement les wrfrst de l'instant $1 (fin de la fenetre), pour la suivante
garder_dernier_restart()
{
	local fichier
	for fichier in wrfrst_d0*; do
		[ -e "$fichier" ] || continue
		[ "$(instant_wrfout "$fichier")" = "$1" ] || rm -f "$fichier"
	done
}

## Controle d'une serie assemblee : temps strictement croissant
controler_serie()
{
	awk 'NR == 1 { next } NF == 0 { next }
	{
		t = ($1 ~ /^[0-9]+$/ && NF > 2 && $2 ~ /\./) ? $2 : $1
		if (NR > 2 && t + 0 <= precedent + 0) { print "temps non croissant ligne " NR; exit 3 }
		precedent = t
	}' "$1" > /dev/null
}

## Fenetres d'un bloc, dans l'ordre chronologique (lues dans le plan)
fenetres_du_bloc()
{
	awk -F, -v bloc="$1" 'NR > 1 && $3 == bloc { printf "%s ", $1 }' "$PLAN"
}

## Vrai si l'etape est deja faite (lue dans le fichier d'etat) : "fenetre 012", "bloc 2024-03"
deja_fait()
{
	grep -qE "^$1( |\$)" "$ETAT"
}

## Temps restant du calcul Slurm, en secondes ; -1 hors Slurm ou s'il est inconnu (sans limite)
temps_restant()
{
	local texte jours=0 parties
	if [ -z "${SLURM_JOB_ID:-}" ] || ! command -v squeue > /dev/null; then
		echo -1
		return
	fi
	texte=$(squeue -h -j "$SLURM_JOB_ID" -o %L 2> /dev/null | head -n 1 | tr -d '[:space:]')
	if [[ ! "$texte" =~ ^([0-9]+-)?[0-9]+(:[0-9]+){0,2}$ ]]; then
		echo -1
		return
	fi
	if [[ "$texte" == *-* ]]; then
		jours=${texte%%-*}
		texte=${texte#*-}
	fi
	IFS=: read -r -a parties <<< "$texte"
	while (( ${#parties[@]} < 3 )); do
		parties=(0 "${parties[@]}")
	done
	echo $(( 10#$jours * 86400 + 10#${parties[0]} * 3600 + 10#${parties[1]} * 60 + 10#${parties[2]} ))
}

## Vrai s'il reste le temps de calculer une fenetre de $1 secondes simulees. Estimation : la
## fenetre deja faite la plus lente (temps reel / temps simule), plus 20 % et 10 min de marge.
## $2 : fenetres deja faites par ce calcul-ci
assez_de_temps()
{
	local duree=$1 faites_ici=$2 restant estime
	restant=$(temps_restant)
	(( restant >= 0 )) || return 0
	estime=$(awk -v duree="$duree" '$1 == "fenetre" && $4 > 0 { r = $3 / $4; if (r > max) max = r; n++ }
		END { if (n == 0) print -1; else printf "%d\n", duree * max * 1.2 + 600 }' "$ETAT")
	(( estime >= 0 )) || return 0
	(( restant >= estime )) && return 0
	(( faites_ici > 0 )) || echec "une fenetre demande environ $(( estime / 3600 )) h $(( estime % 3600 / 60 )) min, plus que la duree d'un calcul Slurm : augmentez --time ou le nombre de coeurs"
	return 1
}

## Relance ce meme script pour la suite (il demarre a la fin de ce calcul), puis s'arrete
relancer()
{
	journal "Plus assez de temps dans ce calcul Slurm pour la fenetre suivante : relance de ${SCRIPT_WRF}"
	if command -v sbatch > /dev/null && sbatch --dependency="afterany:${SLURM_JOB_ID}" "$SCRIPT_WRF"; then
		journal "Le nouveau calcul reprendra a la fenetre suivante"
		exit 0
	fi
	echec "relance impossible : depuis ce dossier, lancez de nouveau 'sbatch ${SCRIPT_WRF}', il reprendra a la fenetre suivante"
}

## Assemble les series d'un bloc dans l'ordre chronologique : tslist_blocs/<nom>.dNN.<VAR>.<bloc>
assembler_bloc()
{
	local bloc=$1 ids id fichier base produit premier
	deja_fait "bloc ${bloc}" && return 0
	ids=$(fenetres_du_bloc "$bloc")
	ids=${ids% }
	mkdir -p tslist_blocs
	for fichier in tslist_fenetres/*."${ids%% *}"; do
		[ -e "$fichier" ] || continue
		base=$(basename "${fichier%.*}")
		produit="tslist_blocs/${base}.${bloc}"
		premier=1
		for id in $ids; do
			[ -f "tslist_fenetres/${base}.${id}" ] || echec "serie manquante : ${base} (fenetre ${id})"
			if (( premier )); then
				cat "tslist_fenetres/${base}.${id}"
				premier=0
			else
				tail -n +2 "tslist_fenetres/${base}.${id}"
			fi
		done > "${produit}.tmp"
		controler_serie "${produit}.tmp" || echec "controle de ${produit}"
		mv "${produit}.tmp" "$produit"
		for id in $ids; do rm -f "tslist_fenetres/${base}.${id}"; done
	done
	echo "bloc ${bloc}" >> "$ETAT"
	journal "Bloc ${bloc} assemble"
}
""",
    "en": r"""
## time_control dates of a window: $1 start, $2 end, $3 duration (s), $4 restart (1: starts
## from the wrfrst of the previous window). run_* and end_* agree: WRF gives priority to
## run_*. Continuous: a wrfrst is written at the end of every window.
wrf_dates()
{
	local start=$1 end=$2 duration=$3 restarted=$4 when date
	for when in start end; do
		if [ "$when" = start ]; then date=$start; else date=$end; fi
		set_option namelist.input "${when}_year" "$(per_domain "${date:0:4}")"
		set_option namelist.input "${when}_month" "$(per_domain "$((10#${date:5:2}))")"
		set_option namelist.input "${when}_day" "$(per_domain "$((10#${date:8:2}))")"
		set_option namelist.input "${when}_hour" "$(per_domain "$((10#${date:11:2}))")"
		set_option namelist.input "${when}_minute" "$(per_domain "$((10#${date:14:2}))")"
		set_option namelist.input "${when}_second" "$(per_domain "$((10#${date:17:2}))")"
	done
	set_option namelist.input run_days "0,"
	set_option namelist.input run_hours "$(( duration / 3600 )),"
	set_option namelist.input run_minutes "$(( duration % 3600 / 60 )),"
	set_option namelist.input run_seconds "$(( duration % 60 )),"
	if (( restarted )); then
		set_option namelist.input restart ".true.,"
	else
		set_option namelist.input restart ".false.,"
	fi
	(( CONTINUOUS == 0 )) || set_option namelist.input restart_interval "$(( duration / 60 )),"
}

## Runs real.exe or wrf.exe and checks SUCCESS COMPLETE
run_wrf_program()
{
	local program=$1 expected=$2 output=$3
	rm -f rsl.out.* rsl.error.*
	log_line "  > ${program}..."
	# shellcheck disable=SC2086
	$LAUNCHER "./${program}" > "$output" 2>&1
	local code=$?
	if [ -f rsl.error.0000 ]; then
		cp rsl.error.0000 "${output%.txt}.rsl.txt"
		grep -q "$expected" rsl.error.0000 \
			|| fail "${program}: no '${expected}' in rsl.error.0000 (see ${output%.txt}.rsl.txt)"
	else
		grep -q "$expected" "$output" || fail "${program}: no '${expected}' (see ${output})"
	fi
	(( code == 0 )) || log_line "  ${program} returned code ${code} despite SUCCESS COMPLETE"
}

## Number of metgrid levels, read in the first met_em of domain 1
metgrid_levels()
{
	local first levels soil
	if [ -n "$METGRID_LEVELS" ]; then
		set_option namelist.input num_metgrid_levels "${METGRID_LEVELS},"
		return
	fi
	first=$(find . -maxdepth 1 -name 'met_em.d01.*' | sort | head -n 1)
	[ -n "$first" ] || fail "no met_em.d01 in ${MET_EM_DIR}"
	command -v ncdump > /dev/null \
		|| fail "ncdump not found: set METGRID_LEVELS in the basic settings"
	levels=$(ncdump -h "$first" | sed -n -E 's/^[[:space:]]*num_metgrid_levels = ([0-9]+) ;/\1/p')
	soil=$(ncdump -h "$first" | sed -n -E 's/^[[:space:]]*:NUM_METGRID_SOIL_LEVELS = ([0-9]+) ;/\1/p')
	[ -n "$levels" ] && [ -n "$soil" ] || fail "levels unreadable in ${first}"
	set_option namelist.input num_metgrid_levels "${levels},"
	set_option namelist.input num_metgrid_soil_levels "${soil},"
}

## Cuts a tslist series of a window: keeps ]useful start, useful end], the time becomes hours
## since D, the header takes the date D. Fixed step: by step number, with a check of the line
## counts; adaptive step: by time. After a restart (no spin-up), the time counts from the start
## of the window or from the very first start: both are recognised.
## $1 raw file, $2 time column, $3 domain (1, 2...), $4 last kept step,
## $5 offset (s), $6 simulated duration (s), $7 product file, $8 restart (1: starts from a wrfrst),
## $9 spin-up of the window (s; 0 after a restart)
cut_series()
{
	local raw=$1 column=$2 domain=$3 last=$4 offset=$5 duration=$6 product=$7 restarted=$8
	local spin_up=$9
	local num=${STEP_NUM[domain-1]} den=${STEP_DEN[domain-1]}
	# First kept step: floor(spin-up / dt) + 1
	local first=$(( spin_up * den / num + 1 ))
	awk -v col="$column" -v num="$num" -v den="$den" -v n0="$first" -v n1="$last" \
		-v off="$offset" -v spin="$spin_up" -v duration="$duration" \
		-v restarted="$restarted" -v base="$(( offset + SPIN_UP_S ))" \
		-v adaptive="$ADAPTIVE_STEP" -v date_d="$STUDY_START" '
	NR == 1 {
		header = $0
		sub(/[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9]_[0-9][0-9]:[0-9][0-9]:[0-9][0-9][ \t]*$/, date_d, header)
		print header
		next
	}
	NF == 0 { next }
	{
		t = $col * 3600
		if (restarted == 1 && read_lines++ == 0 && t > base / 2) { cumulative = 1 }
		if (cumulative) { t -= base }
		if (adaptive == 1) {
			if (t <= spin + 0.5) { removed++; next }
			if (t > duration + 0.5) { after++; next }
			if (kept > 0 && t <= previous) { problem = "time not increasing line " NR }
			previous = t
			$col = sprintf("%.6f", (off + t) / 3600)
		} else {
			n = int(t * den / num + 0.5)
			if (n < n0) { removed++; next }
			if (n > n1) { after++; next }
			if (kept > 0 && n != awaited) { problem = "missing or repeated step line " NR }
			if (kept == 0 && n != n0) { problem = "first step " n " instead of " n0 }
			awaited = n + 1
			$col = sprintf("%.6f", (off + n * num / den) / 3600)
		}
		kept++
		print
	}
	END {
		if (adaptive != 1) {
			if (removed != n0 - 1) { problem = problem " ; " removed+0 " spin-up lines instead of " n0 - 1 }
			if (kept != n1 - n0 + 1) { problem = problem " ; " kept+0 " kept lines instead of " n1 - n0 + 1 }
		}
		if (problem != "") { print problem > "/dev/stderr"; exit 3 }
	}' "$raw" > "${product}.tmp" || return 1
	mv "${product}.tmp" "$product"
}

## Saves and cuts the tslist series of a window, right after wrf.exe
## $1 id, $2 offset (s), $3 simulated duration (s), $4 restart, $5 spin-up (s),
## $6... last step of each domain
save_tslist()
{
	local id=$1 offset=$2 duration=$3 restarted=$4 spin_up=$5
	shift 5
	local lasts=("$@") name domain variable raw column count=0
	mkdir -p tslist_windows
	for name in "${TSNAME[@]}"; do
		for (( domain = 1; domain <= MAX_DOM; domain++ )); do
			for variable in "${TSVARS[@]}"; do
				raw="${name}.d$(printf '%02d' "$domain").${variable}"
				[ -f "$raw" ] || continue
				if [ "$variable" = TS ]; then column=2; else column=1; fi
				cut_series "$raw" "$column" "$domain" "${lasts[domain-1]}" \
					"$offset" "$duration" "tslist_windows/${raw}.${id}" "$restarted" "$spin_up" \
					|| fail "cutting ${raw} (window ${id})"
				rm -f "$raw"
				(( count += 1 ))
			done
		done
	done
	log_line "  > ${count} tslist series cut"
}

## Continuous: true if the wrfrst_d01 of time $1 (end of the previous window) is here
restart_present()
{
	local file
	for file in wrfrst_d01_*; do
		[ -e "$file" ] || continue
		[ "$(wrfout_time "$file")" = "$1" ] && return 0
	done
	return 1
}

## Continuous: keeps only the wrfrst of time $1 (end of the window), for the next one
keep_last_restart()
{
	local file
	for file in wrfrst_d0*; do
		[ -e "$file" ] || continue
		[ "$(wrfout_time "$file")" = "$1" ] || rm -f "$file"
	done
}

## Check of an assembled series: time strictly increasing
check_series()
{
	awk 'NR == 1 { next } NF == 0 { next }
	{
		t = ($1 ~ /^[0-9]+$/ && NF > 2 && $2 ~ /\./) ? $2 : $1
		if (NR > 2 && t + 0 <= previous + 0) { print "time not increasing line " NR; exit 3 }
		previous = t
	}' "$1" > /dev/null
}

## Windows of a block, in chronological order (read in the plan)
block_windows()
{
	awk -F, -v block="$1" 'NR > 1 && $3 == block { printf "%s ", $1 }' "$PLAN"
}

## True if the step is already done (read in the state file): "window 012", "block 2024-03"
already_done()
{
	grep -qE "^$1( |\$)" "$STATE"
}

## Time left in the Slurm job, in seconds; -1 outside Slurm or when unknown (no limit)
time_left()
{
	local text days=0 parts
	if [ -z "${SLURM_JOB_ID:-}" ] || ! command -v squeue > /dev/null; then
		echo -1
		return
	fi
	text=$(squeue -h -j "$SLURM_JOB_ID" -o %L 2> /dev/null | head -n 1 | tr -d '[:space:]')
	if [[ ! "$text" =~ ^([0-9]+-)?[0-9]+(:[0-9]+){0,2}$ ]]; then
		echo -1
		return
	fi
	if [[ "$text" == *-* ]]; then
		days=${text%%-*}
		text=${text#*-}
	fi
	IFS=: read -r -a parts <<< "$text"
	while (( ${#parts[@]} < 3 )); do
		parts=(0 "${parts[@]}")
	done
	echo $(( 10#$days * 86400 + 10#${parts[0]} * 3600 + 10#${parts[1]} * 60 + 10#${parts[2]} ))
}

## True if there is time left to compute a window of $1 simulated seconds. Estimate: the slowest
## window done so far (real time / simulated time), plus 20 % and a 10 min margin.
## $2: windows already done by this very job
enough_time()
{
	local duration=$1 done_here=$2 left estimate
	left=$(time_left)
	(( left >= 0 )) || return 0
	estimate=$(awk -v duration="$duration" '$1 == "window" && $4 > 0 { r = $3 / $4; if (r > max) max = r; n++ }
		END { if (n == 0) print -1; else printf "%d\n", duration * max * 1.2 + 600 }' "$STATE")
	(( estimate >= 0 )) || return 0
	(( left >= estimate )) && return 0
	(( done_here > 0 )) || fail "a window needs about $(( estimate / 3600 )) h $(( estimate % 3600 / 60 )) min, more than a Slurm job lasts: raise --time or the number of cores"
	return 1
}

## Submits this same script again for what remains (it starts when this job ends), then stops
relaunch()
{
	log_line "Not enough time left in this Slurm job for the next window: ${WRF_SCRIPT} submitted again"
	if command -v sbatch > /dev/null && sbatch --dependency="afterany:${SLURM_JOB_ID}" "$WRF_SCRIPT"; then
		log_line "The new job will resume at the next window"
		exit 0
	fi
	fail "cannot submit again: from this folder, run 'sbatch ${WRF_SCRIPT}' again, it will resume at the next window"
}

## Assembles the series of a block in chronological order: tslist_blocks/<name>.dNN.<VAR>.<block>
assemble_block()
{
	local block=$1 ids id file base product first
	already_done "block ${block}" && return 0
	ids=$(block_windows "$block")
	ids=${ids% }
	mkdir -p tslist_blocks
	for file in tslist_windows/*."${ids%% *}"; do
		[ -e "$file" ] || continue
		base=$(basename "${file%.*}")
		product="tslist_blocks/${base}.${block}"
		first=1
		for id in $ids; do
			[ -f "tslist_windows/${base}.${id}" ] || fail "missing series: ${base} (window ${id})"
			if (( first )); then
				cat "tslist_windows/${base}.${id}"
				first=0
			else
				tail -n +2 "tslist_windows/${base}.${id}"
			fi
		done > "${product}.tmp"
		check_series "${product}.tmp" || fail "check of ${product}"
		mv "${product}.tmp" "$product"
		for id in $ids; do rm -f "tslist_windows/${base}.${id}"; done
	done
	echo "block ${block}" >> "$STATE"
	log_line "Block ${block} assembled"
}
""",
}

WRF_PROGRAM = {
    "fr": r"""
set -u
debut_script=$(date -u '+%Y-%m-%d %H:%M:%S')
SECONDS=0

## Executables et tables de WRF ; les fichiers de ce dossier (namelist.input, tables des
## eoliennes du projet...) ne sont jamais remplaces
resoudre_dossier DOSSIER_WRF main/wrf.exe "WRF (main/wrf.exe)"
lier "$DOSSIER_WRF/main/real.exe"
lier "$DOSSIER_WRF/main/wrf.exe"
for fichier in "$DOSSIER_WRF"/run/*; do
	case $(basename "$fichier") in
		*.exe) ;;
		*) lier "$fichier" ;;
	esac
done
for fichier in "$DOSSIER_MET_EM"/met_em.d*; do
	[ -e "$fichier" ] || echec "aucun met_em dans ${DOSSIER_MET_EM} : lancez d'abord WPS"
	ln -sf "$fichier" .
done
niveaux_metgrid
mkdir -p journaux
touch "$ETAT"

## Fenetres du plan, dans l'ordre de calcul (antichronologique ; chronologique en continu) ;
## celles deja faites (fichier d'etat) sont sautees : relance apres un arret, le script reprend
## a la fenetre suivante
mapfile -t fenetres < <(tail -n +2 "$PLAN" | sort -t, -k2,2n)
(( ${#fenetres[@]} > 0 )) || echec "aucune fenetre dans ${PLAN}"
[ -s "$ETAT" ] && journal "Reprise : les etapes deja faites sont lues dans ${ETAT}"
bloc_en_cours=""
faites_ici=0
for ligne in "${fenetres[@]}"; do
	IFS=, read -r id _ bloc debut fin debut_utile fin_utile _ _ duree decalage reprise mise_en_route fin_real duree_real pas_finaux <<< "$ligne"
	IFS=, read -r -a derniers <<< "$pas_finaux"
	if [ -n "$bloc_en_cours" ] && [ "$bloc" != "$bloc_en_cours" ]; then
		assembler_bloc "$bloc_en_cours"
	fi
	bloc_en_cours=$bloc
	deja_fait "fenetre ${id}" && continue
	assez_de_temps "$duree" "$faites_ici" || relancer
	journal "Fenetre ${id} (bloc ${bloc}) : simulation ${debut} -> ${fin}, utile ]${debut_utile}, ${fin_utile}]"
	debut_fenetre=$SECONDS
	(( reprise == 0 )) || restart_present "$debut" \
		|| echec "pas de wrfrst_d01 du ${debut} : la fenetre precedente doit etre faite d'abord"
	# real.exe prepare jusqu'a l'instant des donnees qui suit la fin ; wrf.exe s'arrete a la fin
	dates_wrf "$debut" "$fin_real" "$duree_real" "$reprise"
	executer_wrf real.exe "SUCCESS COMPLETE REAL_EM INIT" "journaux/real_${id}.txt"
	dates_wrf "$debut" "$fin" "$duree" "$reprise"
	cp namelist.input "journaux/namelist.input.${id}"
	executer_wrf wrf.exe "SUCCESS COMPLETE WRF" "journaux/wrf_${id}.txt"
	sauver_tslist "$id" "$decalage" "$duree" "$reprise" "$mise_en_route" "${derniers[@]}"
	(( CONTINU == 0 )) || garder_dernier_restart "$fin"
	echo "fenetre ${id} $(( SECONDS - debut_fenetre )) ${duree}" >> "$ETAT"
	(( faites_ici += 1 ))
done
assembler_bloc "$bloc_en_cours"

journal "Toutes les fenetres sont faites : assemblage de la periode"
assembler_periode
journal "Termine. Debut : ${debut_script} UTC ; duree : $(( SECONDS / 3600 )) h $(( SECONDS % 3600 / 60 )) min"
exit 0
""",
    "en": r"""
set -u
script_start=$(date -u '+%Y-%m-%d %H:%M:%S')
SECONDS=0

## WRF executables and tables; the files of this folder (namelist.input, turbine tables of the
## project...) are never replaced
resolve_folder WRF_DIR main/wrf.exe "WRF (main/wrf.exe)"
link_here "$WRF_DIR/main/real.exe"
link_here "$WRF_DIR/main/wrf.exe"
for file in "$WRF_DIR"/run/*; do
	case $(basename "$file") in
		*.exe) ;;
		*) link_here "$file" ;;
	esac
done
for file in "$MET_EM_DIR"/met_em.d*; do
	[ -e "$file" ] || fail "no met_em in ${MET_EM_DIR}: run WPS first"
	ln -sf "$file" .
done
metgrid_levels
mkdir -p logs
touch "$STATE"

## Windows of the plan, in the order of computation (antichronological; chronological when
## continuous); those already done (state file) are skipped: run again after a stop, the script
## resumes at the next window
mapfile -t windows < <(tail -n +2 "$PLAN" | sort -t, -k2,2n)
(( ${#windows[@]} > 0 )) || fail "no window in ${PLAN}"
[ -s "$STATE" ] && log_line "Resuming: the steps already done are read in ${STATE}"
current_block=""
done_here=0
for line in "${windows[@]}"; do
	IFS=, read -r id _ block start end useful_start useful_end _ _ duration offset restarted spin_up real_end real_duration last_steps <<< "$line"
	IFS=, read -r -a lasts <<< "$last_steps"
	if [ -n "$current_block" ] && [ "$block" != "$current_block" ]; then
		assemble_block "$current_block"
	fi
	current_block=$block
	already_done "window ${id}" && continue
	enough_time "$duration" "$done_here" || relaunch
	log_line "Window ${id} (block ${block}): simulation ${start} -> ${end}, useful ]${useful_start}, ${useful_end}]"
	window_start=$SECONDS
	(( restarted == 0 )) || restart_present "$start" \
		|| fail "no wrfrst_d01 of ${start}: the previous window must be done first"
	# real.exe prepares up to the data time after the end; wrf.exe stops at the end
	wrf_dates "$start" "$real_end" "$real_duration" "$restarted"
	run_wrf_program real.exe "SUCCESS COMPLETE REAL_EM INIT" "logs/real_${id}.txt"
	wrf_dates "$start" "$end" "$duration" "$restarted"
	cp namelist.input "logs/namelist.input.${id}"
	run_wrf_program wrf.exe "SUCCESS COMPLETE WRF" "logs/wrf_${id}.txt"
	save_tslist "$id" "$offset" "$duration" "$restarted" "$spin_up" "${lasts[@]}"
	(( CONTINUOUS == 0 )) || keep_last_restart "$end"
	echo "window ${id} $(( SECONDS - window_start )) ${duration}" >> "$STATE"
	(( done_here += 1 ))
done
assemble_block "$current_block"

log_line "Every window is done: assembly of the period"
assemble_period
log_line "Done. Start: ${script_start} UTC; duration: $(( SECONDS / 3600 )) h $(( SECONDS % 3600 / 60 )) min"
exit 0
""",
}

CONCATENATE_FUNCTIONS = {
    "fr": r"""
## Instant d'un wrfout d'apres son nom (avec ou sans deux-points)
instant_wrfout()
{
	local nom=${1##*/}
	nom=${nom:11:19}
	echo "${nom:0:13}:${nom:14:2}:${nom:17:2}"
}

## Fenetre dont l'intervalle utile ]debut, fin] contient l'instant, ou la 1re pour D
debut_attendu()
{
	local instant=$1 ligne debut fin simulation
	for ligne in "${FENETRES_UTILES[@]}"; do
		read -r debut fin simulation <<< "$ligne"
		if [[ "$instant" > "$debut" && ! "$instant" > "$fin" ]]; then
			echo "$simulation"
			return
		fi
	done
	read -r _ _ simulation <<< "${FENETRES_UTILES[0]}"
	echo "$simulation"
}
""",
    "en": r"""
## Time of a wrfout from its name (with or without colons)
wrfout_time()
{
	local name=${1##*/}
	name=${name:11:19}
	echo "${name:0:13}:${name:14:2}:${name:17:2}"
}

## Window whose useful interval ]start, end] holds the time, or the 1st one for D
expected_start()
{
	local stamp=$1 line start end simulation
	for line in "${USEFUL_WINDOWS[@]}"; do
		read -r start end simulation <<< "$line"
		if [[ "$stamp" > "$start" && ! "$stamp" > "$end" ]]; then
			echo "$simulation"
			return
		fi
	done
	read -r _ _ simulation <<< "${USEFUL_WINDOWS[0]}"
	echo "$simulation"
}
""",
}

ASSEMBLY_FUNCTION = {
    "fr": r"""
## Assemblage de la periode, apres la derniere fenetre : series tslist sur ]D, F], wrfout
## de mise en route mis de cote, controle des instants et de l'origine de chaque wrfout
assembler_periode()
{
	# Blocs dans l'ordre chronologique ; fenetres : debut utile | fin utile | debut de simulation
	mapfile -t BLOCS < <(awk -F, 'NR > 1 && !vu[$3]++ { print $3 }' "$PLAN")
	mapfile -t FENETRES_UTILES < <(awk -F, 'NR > 1 { print $6, $7, $4 }' "$PLAN")
	read -r _ _ debut_initial <<< "${FENETRES_UTILES[0]}"
	## 1- Series tslist sur toute la periode : tslist_periode/<nom>.dNN.<VAR>
	mkdir -p tslist_periode
	premier_bloc=${BLOCS[0]}
	for fichier in tslist_blocs/*."${premier_bloc}"; do
		[ -e "$fichier" ] || continue
		base=$(basename "${fichier%."${premier_bloc}"}")
		premier=1
		for bloc in "${BLOCS[@]}"; do
			[ -f "tslist_blocs/${base}.${bloc}" ] || echec "serie manquante : ${base} (bloc ${bloc})"
			if (( premier )); then
				cat "tslist_blocs/${base}.${bloc}"
				premier=0
			else
				tail -n +2 "tslist_blocs/${base}.${bloc}"
			fi
		done > "tslist_periode/${base}.tmp"
		domaine=$(( 10#$(echo "$base" | sed -E 's/.*\.d([0-9][0-9])\.[A-Z0-9]+$/\1/') ))
		attendu=${LIGNES_ATTENDUES[domaine-1]}
		lignes=$(( $(grep -c . "tslist_periode/${base}.tmp") - 1 ))
		if [ "$attendu" != "-" ] && (( lignes != attendu )); then
			echec "${base} : ${lignes} lignes au lieu de ${attendu}"
		fi
		awk -v pas="${PAS_S[domaine-1]}" -v constant="${PAS_CONSTANT[domaine-1]}" '
		NR == 1 || NF == 0 { next }
		{
			t = ($1 ~ /^[0-9]+$/ && NF > 2 && $2 ~ /\./) ? $2 : $1
			if (NR > 2) {
				if (t + 0 <= precedent + 0) { print "temps non croissant ligne " NR; exit 3 }
				ecart = (t - precedent) * 3600
				if (constant == 1 && (ecart - pas > 0.01 || pas - ecart > 0.01)) {
					print "pas de " ecart " s au lieu de " pas " ligne " NR; exit 3
				}
			}
			precedent = t
		}' "tslist_periode/${base}.tmp" > "tslist_periode/${base}.controle" || echec "${base} : $(cat "tslist_periode/${base}.controle")"
		rm -f "tslist_periode/${base}.controle"
		mv "tslist_periode/${base}.tmp" "tslist_periode/${base}"
	done
	journal "Series tslist assemblees dans tslist_periode/ (temps en heures depuis ${DEBUT_ETUDE})"

	## 2- wrfout : ceux d'avant D (mise en route de la 1re fenetre) sont mis de cote
	mkdir -p "$DOSSIER_MISE_EN_ROUTE"
	deplaces=0
	for fichier in wrfout_d0*; do
		[ -e "$fichier" ] || continue
		instant=$(instant_wrfout "$fichier")
		if [[ "$instant" < "$DEBUT_ETUDE" ]]; then
			mv "$fichier" "$DOSSIER_MISE_EN_ROUTE/"
			(( deplaces += 1 ))
		fi
	done
	journal "${deplaces} wrfout de mise en route deplaces dans ${DOSSIER_MISE_EN_ROUTE}/"

	## 3- Controle : exactement les instants attendus sur [D, F], et l'origine de chaque fichier
	erreurs=0
	for (( domaine = 1; domaine <= MAX_DOM; domaine++ )); do
		nombre=0
		for fichier in "wrfout_d$(printf '%02d' "$domaine")"_*; do
			[ -e "$fichier" ] || continue
			instant=$(instant_wrfout "$fichier")
			if [[ "$instant" > "$FIN_ETUDE" ]]; then
				journal "wrfout apres F : ${fichier}"
				(( erreurs += 1 ))
			fi
			if (( VERIFIER_ORIGINE )) && command -v ncdump > /dev/null; then
				origine=$(ncdump -h "$fichier" | sed -n -E 's/^[[:space:]]*:START_DATE = "([^"]+)" ;/\1/p')
				attendue=$(debut_attendu "$instant")
				# En continu, WRF peut garder la date du tout premier depart
				if (( CONTINU )) && [ "$origine" = "$debut_initial" ]; then
					attendue=$origine
				fi
				if [ "$origine" != "$attendue" ]; then
					journal "${fichier} vient de la simulation commencee le ${origine}, attendu ${attendue}"
					(( erreurs += 1 ))
				fi
			fi
			(( nombre += 1 ))
		done
		attendu=${INSTANTS_ATTENDUS[domaine-1]}
		if (( nombre != attendu )); then
			journal "domaine ${domaine} : ${nombre} wrfout au lieu de ${attendu} (toutes les ${SORTIES_S[domaine-1]} s de D a F)"
			(( erreurs += 1 ))
		fi
	done
	(( erreurs == 0 )) || echec "${erreurs} anomalie(s) dans les wrfout"
	journal "wrfout controles : exactement les instants de [${DEBUT_ETUDE}, ${FIN_ETUDE}]"
}
""",
    "en": r"""
## Assembly of the period, after the last window: tslist series over ]D, F], spin-up
## wrfout set aside, check of the times and of the origin of each wrfout
assemble_period()
{
	# Blocks in chronological order; windows: useful start | useful end | simulation start
	mapfile -t BLOCKS < <(awk -F, 'NR > 1 && !seen[$3]++ { print $3 }' "$PLAN")
	mapfile -t USEFUL_WINDOWS < <(awk -F, 'NR > 1 { print $6, $7, $4 }' "$PLAN")
	read -r _ _ first_start <<< "${USEFUL_WINDOWS[0]}"
	## 1- tslist series over the whole period: tslist_period/<name>.dNN.<VAR>
	mkdir -p tslist_period
	first_block=${BLOCKS[0]}
	for file in tslist_blocks/*."${first_block}"; do
		[ -e "$file" ] || continue
		base=$(basename "${file%."${first_block}"}")
		first=1
		for block in "${BLOCKS[@]}"; do
			[ -f "tslist_blocks/${base}.${block}" ] || fail "missing series: ${base} (block ${block})"
			if (( first )); then
				cat "tslist_blocks/${base}.${block}"
				first=0
			else
				tail -n +2 "tslist_blocks/${base}.${block}"
			fi
		done > "tslist_period/${base}.tmp"
		domain=$(( 10#$(echo "$base" | sed -E 's/.*\.d([0-9][0-9])\.[A-Z0-9]+$/\1/') ))
		expected=${EXPECTED_LINES[domain-1]}
		lines=$(( $(grep -c . "tslist_period/${base}.tmp") - 1 ))
		if [ "$expected" != "-" ] && (( lines != expected )); then
			fail "${base}: ${lines} lines instead of ${expected}"
		fi
		awk -v step="${STEP_S[domain-1]}" -v constant="${CONSTANT_STEP[domain-1]}" '
		NR == 1 || NF == 0 { next }
		{
			t = ($1 ~ /^[0-9]+$/ && NF > 2 && $2 ~ /\./) ? $2 : $1
			if (NR > 2) {
				if (t + 0 <= previous + 0) { print "time not increasing line " NR; exit 3 }
				gap = (t - previous) * 3600
				if (constant == 1 && (gap - step > 0.01 || step - gap > 0.01)) {
					print "step of " gap " s instead of " step " line " NR; exit 3
				}
			}
			previous = t
		}' "tslist_period/${base}.tmp" > "tslist_period/${base}.check" || fail "${base}: $(cat "tslist_period/${base}.check")"
		rm -f "tslist_period/${base}.check"
		mv "tslist_period/${base}.tmp" "tslist_period/${base}"
	done
	log_line "tslist series assembled in tslist_period/ (time in hours since ${STUDY_START})"

	## 2- wrfout: those before D (spin-up of the 1st window) are set aside
	mkdir -p "$SPIN_UP_DIR"
	moved=0
	for file in wrfout_d0*; do
		[ -e "$file" ] || continue
		stamp=$(wrfout_time "$file")
		if [[ "$stamp" < "$STUDY_START" ]]; then
			mv "$file" "$SPIN_UP_DIR/"
			(( moved += 1 ))
		fi
	done
	log_line "${moved} spin-up wrfout moved to ${SPIN_UP_DIR}/"

	## 3- Check: exactly the expected times of [D, F], and the origin of each file
	errors=0
	for (( domain = 1; domain <= MAX_DOM; domain++ )); do
		count=0
		for file in "wrfout_d$(printf '%02d' "$domain")"_*; do
			[ -e "$file" ] || continue
			stamp=$(wrfout_time "$file")
			if [[ "$stamp" > "$STUDY_END" ]]; then
				log_line "wrfout after F: ${file}"
				(( errors += 1 ))
			fi
			if (( CHECK_ORIGIN )) && command -v ncdump > /dev/null; then
				origin=$(ncdump -h "$file" | sed -n -E 's/^[[:space:]]*:START_DATE = "([^"]+)" ;/\1/p')
				awaited=$(expected_start "$stamp")
				# Continuous: WRF may keep the date of the very first start
				if (( CONTINUOUS )) && [ "$origin" = "$first_start" ]; then
					awaited=$origin
				fi
				if [ "$origin" != "$awaited" ]; then
					log_line "${file} comes from the simulation started on ${origin}, expected ${awaited}"
					(( errors += 1 ))
				fi
			fi
			(( count += 1 ))
		done
		expected=${EXPECTED_TIMES[domain-1]}
		if (( count != expected )); then
			log_line "domain ${domain}: ${count} wrfout instead of ${expected} (every ${OUTPUT_S[domain-1]} s from D to F)"
			(( errors += 1 ))
		fi
	done
	(( errors == 0 )) || fail "${errors} anomaly(ies) in the wrfout"
	log_line "wrfout checked: exactly the times of [${STUDY_START}, ${STUDY_END}]"
}
""",
}
