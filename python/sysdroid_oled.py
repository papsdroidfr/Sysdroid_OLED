#!/usr/bin/env python3
########################################################################
# Filename    : sysDroid_oled.py
# Description : information système raspberry pi (température, CPU, mémoire) sur écran OLED 128x64
# auther      : papsdroid.fr
# modification: 2021/05/01
########################################################################
import time, os, threading, psutil
import board, digitalio
from PIL import Image, ImageDraw, ImageFont
import adafruit_ssd1306

#classe gestion d'affichage sur OLED i2c 128x64 pix
class Oled():
    def __init__(self, width=128, height=64, border=1):
        self.oled_reset = digitalio.DigitalInOut(board.D4)
        self.width, self.height, self.border = width, height, border
        self.i2c = board.I2C()
        self.oled = adafruit_ssd1306.SSD1306_I2C(self.width, self.height, self.i2c, addr=0x3C, reset=self.oled_reset)
        self.clear()
        # Create blank image for drawing.
        # Make sure to create image with mode '1' for 1-bit color.
        self.image = Image.new("1", (self.oled.width, self.oled.height))
        # Get drawing object to draw on image.
        self.draw = ImageDraw.Draw(self.image)
        self.font = ImageFont.load_default()
        self.font_rd = ImageFont.truetype(font="/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", size=14)
        self.font_t = ImageFont.truetype(font="/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", size=20)
        self.titre_cpu = 'CPUs'
        self.titre_ram = 'R'
        self.titre_disk = 'D'
        self.font_width_cpu,  self.font_height_cpu  = self.font.getsize(self.titre_cpu)
        self.font_width_ram,  self.font_height_ram  = self.font_rd.getsize(self.titre_ram)
        self.font_width_disk, self.font_height_disk = self.font_rd.getsize(self.titre_disk)

    def clear(self):
        # Clear display
        self.oled.fill(0)
        self.oled.show()

    def draw_jauge_v(self, x, y, width=10, height=48, level=0):
        # affiche une jauge verticale [0-100%] en x,y = point bas gauche de la jauge,
        # heigth = hauteur quand level = 100%
        height_loss = (height*level)//100 #hauteur de la jauge selon level
        self.draw.rectangle((x, y, x+width-1, y-height_loss-1), fill=255, outline=255, width=1)
        self.draw.line((x+width//2, y, x+width//2, y-height-1), fill=255, width=1)
    
    def draw_jauge_h(self, x, y, width=44, height=10, level=0):
        # affiche une jauge horizontale [0-100%] en x,y = point haut gauche de la jauge,
        # heigth = hauteur quand level = 100%
        width_level = (width*level)//100 #hauteur de la jauge selon level
        self.draw.rectangle((x, y, x+width_level-1, y+height-1), fill=255, outline=255, width=1)
        self.draw.line((x,y+height//2, x+width-1, y+height//2), fill=255, width=1)
        
    def draw_levels(self, cpus, ram, disk, temp): 
        # cadres fixes
        self.draw.rectangle((0,0,self.oled.width-1, self.oled.height-1), fill=0, outline=255, width=1)    # cadre
        self.draw.line((self.oled.width//2, 0, self.oled.width//2, self.oled.height-1),                   # ligne verticale
                       fill=255,width=1)                    
        self.draw.line((self.oled.width//2, self.oled.height//2, self.oled.width-1, self.oled.height//2), # ligne horizontale
                       fill=255, width=1)
        #titres
        self.draw.text((32-self.font_width_cpu//2, 0),  self.titre_cpu, font=self.font, fill=255) # CPU
        self.draw.text((68,6-self.font_height_ram//2),  self.titre_ram, font=self.font_rd, fill=255) # RAM
        self.draw.text((68,22-self.font_height_disk//2), self.titre_disk,font=self.font_rd, fill=255) # Disk
        
        #CPUs level
        for n in range(4):
            self.draw_jauge_v(16*n+3, self.height-3, level=cpus [n])
        #RAM level
        self.draw_jauge_h(80, 9-self.font_height_ram//2, level=ram)
        #Disk level
        self.draw_jauge_h(80, 25-self.font_height_disk//2, level=disk)
        #Température
        t_text = str(temp)+'°C'
        font_width_t,  font_height_t  = self.font_t.getsize(t_text)
        self.draw.text((96-font_width_t//2, 46-font_height_t//2), t_text, font=self.font_t, fill=255) 
 
        self.oled.image(self.image)
        self.oled.show()
        

#classe affichage infos système (via thread)
#-----------------------------------------------------------------------------------------
class SysDroid(threading.Thread):
    def __init__(self, verbose=False, delay=1):     
        threading.Thread.__init__(self)  # appel au constructeur de la classe mère Thread
        self.etat=False             # état du thread False(non démarré), True (démarré)
        self.verbose = verbose      # True: active les print
        self.delay = delay          # délais en secondes de rafraichissement des infos systèmes
        print ('Sysdroid démarre ... ')
        self.readsys = ReadSys(verbose, delay)    # thread de lecture des informations système 
        self.readsys.start()        # démarrage du thread de lecture des info systèmes
        self.screen = Oled()        # écran Oled du sysdroid
       
    #exécution du thread
    #-------------------
    def run(self):
        self.etat=True
        while (self.etat):
            if not(self.readsys.infoLues):
                self.screen.draw_levels(self.readsys.cpus_util, self.readsys.mem_used, self.readsys.disk_used, self.readsys.cpu_t)
                self.readsys.set_infoLues()
            else:
                time.sleep(0.5) # mise en pause (sinon proc saturé par boucle infinie)
        
    #arrêt du thread
    #---------------
    def stop(self):
        self.etat=False
        self.readsys.stop()     # arret du thread readsys
        print('Sysdroid arrêté')      


#classe de lecture des informations systèmes à lire
#-----------------------------------------------------------------------------------------
class ReadSys(threading.Thread):
    def __init__(self, verbose, delay):
        threading.Thread.__init__(self)  # appel au constructeur de la classe mère Thread
        self.verbose = verbose           # True active les print
        self.delay = delay               # délais en secondes entre chaque nouvelle lecture (30s par défaut)
        self.etat=False                  # état du thread False(non démarré), True (démarré)
        self.t_min = 40                  # température minimale (0% si en dessous)
        self.t_max = 80                  # température maximale (100% si au dessus)
        self.cpu_t=0                     # température du CPU
        self.cpu_t_level = 0             # % T°CPu 0%: <=t_min, 100%: >= t_max
        self.cpu_util   = 0              # CPU global utilisation (%)
        self.cpus_util  = [0,0,0,0]      # CPUs utilisation (%)
        self.mem_used   = 0              # mémoire physique utilisée (%)
        self.disk_used  = 0              # usage du disk à la racine ('/') en %
        self.infoLues   = True           # True si les infos sont prises en compte, False sinon.

    #mise à jour de la variable infoLues à True
    #-------------------------------------------
    def set_infoLues(self):
        self.infoLues=True

    #lecture de la température CPU
    #-----------------------------
    def get_cpu_temp(self):     
        tmp = open('/sys/class/thermal/thermal_zone0/temp')
        cpu = tmp.read()
        tmp.close()
        #return(round(float(cpu)/1000,1)) # format xx.x
        return(round(float(cpu)/1000))    # format xx

    #converti la t° CPU en % entre t_min et t_max
    #-------------------------------------------------------------------
    def convert_cpu_pct(self):
        return (float)(self.cpu_t-self.t_min)/(self.t_max-self.t_min)*100
    
   
    #démarrage du thread
    #-------------------
    def run(self):
        self.etat=True
        if self.verbose:
            print('Thread lecture info système démarré')
        while (self.etat):
            #lecture et stockage des informations système
            self.cpu_t = self.get_cpu_temp()
            self.cpu_t_level = self.convert_cpu_pct()
            self.cpu_util = psutil.cpu_percent()
            self.cpus_util = psutil.cpu_percent(percpu=True)
            self.mem_used = psutil.virtual_memory()[2]
            self.disk_used = psutil.disk_usage('/')[3]
            self.infoLues = False
            if self.verbose:
                print ('CPU:', self.cpu_util,'CPUs:', self.cpus_util,'% MEM used:',self.mem_used,'% CPU T°:', self.cpu_t,'°C', ' DISK:',self.disk_used,'%')
            time.sleep(self.delay)

    #arrêt du thread
    #----------------
    def stop(self):
        self.etat=False
        if self.verbose:
            print('Thread lecture info système stoppé')

#classe application principale
#------------------------------------------------------------------------------
class Application():
    def __init__(self, verbose=False, delay=2):
        self.sysdroid = SysDroid(verbose, delay) 
        self.sysdroid.start()   # démarrage du thread de surveillance système

    def loop(self):
        while True:
            time.sleep(1)
            continue

    def destroy(self):          # fonction exécutée sur appui CTRL-C
        self.sysdroid.stop()    # arrêt du thread de surveillance système       


if __name__ == '__main__':     # Program start from here
    appl=Application(verbose=False, delay=2)  
    try:
        appl.loop()
    except KeyboardInterrupt:  # When 'Ctrl+C' is pressed, the child program destroy() will be  executed.
        appl.destroy()    


