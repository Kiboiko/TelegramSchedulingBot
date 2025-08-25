from typing import List, TypeVar, Iterator
from models import Teacher

T = TypeVar('T')

def get_all_teacher_combinations(teachers: List[Teacher]) -> List[List[Teacher]]:
    return list(generate_combinations(teachers))

def generate_combinations(teachers: List[Teacher]) -> Iterator[List[Teacher]]:
    total_combinations = 1 << len(teachers)
    
    for mask in range(total_combinations):
        combination = []
        for i in range(len(teachers)):
            if (mask & (1 << i)) != 0:
                combination.append(teachers[i])
        if combination:
            yield combination

def contains_teacher(teachers: List[Teacher], teacher: Teacher) -> bool:
    for person in teachers:
        if not person.comparison(teacher):
            return False
    return True