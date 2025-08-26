from models import Person,Teacher,Student

stud1 = Student("Биба","8:00","15:00",1,10)
stud2 = Student("Боба","9:00","14:00",1,5)
teacher = Teacher("Петр", "09:00", "17:00", [1, 2, 3], 1, 15)

print(stud1)
print(stud2)
print(teacher)