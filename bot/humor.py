"""
Biblioteca de humor futbolero argentino para Mister.
Cargadas, apodos, modismos, frases célebres y chistes para condimentar las respuestas.
"""

# --- CARGADAS PARA JUGADORES QUE JUEGAN MAL ---
CARGADAS_MAL = [
    "A {nombre} le dicen 'Espejo de corcho' porque tiene menos reflejos que Abbondanzieri con resaca.",
    "A {nombre} le dicen 'Piquetero' porque tiene menos esfuerzo que uno con plan social.",
    "A {nombre} le dicen 'Las Toninas en abril' porque tiene menos centro que balneario en invierno.",
    "A {nombre} le dicen 'Atari' porque tiene menos definición que una consola del 80.",
    "A {nombre} le dicen 'Radiología' porque con él los radiólogos se llenaron de plata.",
    "{nombre} es tan malo que su doctor le aconsejó dejar el fútbol. No porque esté enfermo, sino porque lo vio jugar.",
    "Che {nombre}, sacale la caja a los botines para jugar, muerto.",
    "A {nombre} no le pongas aerosol en la lesión, ponele Blem que es de madera ese muchacho.",
    "{nombre} tiene la mochila puesta todavía. ¡Dejala en el vestuario, crack!",
    "A {nombre} le dicen 'Control remoto' porque no hace nada y encima se pierde.",
    "A {nombre} le ponés dos medias de distinto color y se caga a patadas solo.",
]

# --- HALAGOS EXAGERADOS PARA JUGADORES BUENOS ---
HALAGOS = [
    "{nombre} gambetea hasta su propia sombra. Messi le pide tips por DM.",
    "Con {nombre} en la cancha sobran los otros 6. Es DT, jugador y aguatero a la vez.",
    "{nombre} no corre, levita. La pelota lo busca sola como un imán."
]

# --- FRASES PARA EMPATES ---
FRASES_EMPATE = [
    "Empate. Como decía Passarella: 'La pelota no dobla'. Y hoy tampoco dobló para ningún lado.",
    "Empataron. Ni para ganar ni para perder sirven estos muertos.",
    "Empate técnico, que en criollo significa que los dos jugaron igual de mal.",
    "Empate. Bilardo diría que ser segundo no vale. Bueno, hoy no fue segundo nadie, así que tranquilos.",
    "El empate es como besar a tu hermana: técnicamente es un beso, pero no te deja satisfecho.",
    "Empataron y el fútbol perdió. Pero bueno, vamos a comer asado igual.",
]

# --- FRASES PARA VICTORIAS ---
FRASES_VICTORIA = [
    "Ganaron los de siempre. Bueno, no siempre, pero hoy sí.",
    "¡Victoria! Como decía el Coco Basile: 'Soy hincha de Sportivo Ganar'.",
    "Ganaron y se lo merecen... ponele. Festejá que la próxima te toca perder.",
    "¡Golazo de resultado! Si Zubeldía los viera diría: 'Hicieron lo que tenían que hacer'.",
    "Ganaron. Ahora cámbiense rápido antes de que se les vaya la suerte.",
]

# --- FRASES PARA DERROTAS ---
FRASES_DERROTA = [
    "Perdieron. Pero como decía Pedernera: 'Si ganás, servís; si perdés, no'. Y bueno, hoy no sirvieron.",
    "Perdieron. Y la culpa no es del que les regaló la primera pelota, ¿por qué no les regaló una caña de pescar?",
    "Perdieron. Bilardo los haría ir a Plaza Constitución a las 6AM a ver laburar a la gente.",
    "Derrota. El fútbol es como el caballo: les soltaron la rienda y los volteó.",
    "Perdieron. Pero tranquilos, es fútbol amateur, acá nadie cobra... ni juega como si cobrara.",
]

# --- MODISMOS FUTBOLEROS ARGENTINOS ---
MODISMOS = [
    "Toco y me voy",
    "La pelota no se mancha",
    "El fútbol es el deporte más lindo y más sano del mundo",
    "Ganar, ganar, ganar y volver a ganar",
    "Hay que ir al frente como los pingüinos, con los huevos por delante",
    "Si hacemos lo que tenemos que hacer nos va a ir bien. Si no, vamos a tener que ir a trabajar",
    "Ser segundo no vale",
    "El fútbol es tan generoso que evitó que ciertos DTs se dedicaran a la medicina",
    "El jugador de fútbol es como el caballo: si lo apretás, responde. Si le soltás la rienda, termina volteando al jinete",
    "Yo le pondría un toldo al día para que siempre sea de noche",
    "La pelota no dobla",
]

# --- CHISTES FUTBOLEROS ---
CHISTES = [
    "¿Cómo se llama el peor jugador japonés? Nikito Nitoko.",
    "Mi doctor me aconsejó dejar el fútbol. No porque esté enfermo, sino porque me vio jugar.",
    "¿Cuál es el colmo de un futbolista? Que le salga un hijo pelota.",
    "Jaimito vuelve del partido: 'Papá, jugué mi mejor partido, metí 3 goles'. '¿Y cómo quedaron?' 'Perdimos 2 a 1'.",
    "Elegí: ¿el fútbol o yo? Preguntame en el entretiempo que ahora estoy ocupado.",
    "¿En qué se parece un informático a un arquero? En que los dos creen que tienen el mejor equipo pero solo sacan cosas de la red.",
    "Amor, estás obsesionado con el fútbol. ¿FALTA? ¿FALTAAA? ¡Si no te toqué!",
]

# --- FRASES DE CANCHA ADAPTABLES ---
FRASES_CANCHA = [
    "¡{nombre}, la próxima tirala autografiada!",
    "¡{nombre}, correte que están jugando!",
    "¡{nombre}, pasate a nafta!",
    "¡{nombre}, movete que te va a mear un perro!",
    "¡{nombre}, hacé de cuenta que estás en el Esperanto y encará a alguien!",
    "¡{nombre}, salí que es sábado!",
    "¡{nombre}, carreño, va un pie después del otro!",
    "Che {nombre}, ¿te pido un remís para volver o llegás solo?",
    "{nombre}, juga tranquilo que no hay alcoholemia.",
    "A {nombre} le putearía pero no sé quién es.",
]

# --- APODOS AUTOMÁTICOS POR DESEMPEÑO ---
APODOS_MALOS = [
    "Fantasma", "Muerto", "Pecho frío", "Tronco", "Paquete", "Perro",
    "Cono", "Poste", "Estatua", "Ladrillo", "Pata de palo", "Mueble",
    "Tortuga", "Ancla", "Parante", "Maceta",
]

APODOS_BUENOS = [
    "Crack", "Fenómeno", "Bestia", "Figura", "Mago", "Genio",
    "Distinto", "Enganche", "Gambetero", "Goleador", "Ídolo", "Caudillo",
    "Zurdo mágico", "Maravilla", "Máquina", "Maestro",
]
