#include <Arduino.h>

void setup() {
  pinMode(27, OUTPUT);
  pinMode(26, OUTPUT);
  pinMode(25, OUTPUT);

for(int hasil = 5; hasil <= 10; hasil++) {
  digitalWrite(27, HIGH);
  digitalWrite(26, LOW);
  digitalWrite(25, HIGH);
  delay(500);
  Serial.println(hasil);
  Serial.print("Angka:  ");
}

}

void loop() {
  // put your main code here, to run repeatedly:
  delay(10); // this speeds up the simulation
}
}
