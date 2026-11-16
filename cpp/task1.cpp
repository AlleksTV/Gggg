#include <iostream>
using namespace std;

void sortArray(int a[], int n, bool desc = false) {
    for (int i = 0; i < n - 1; i++)
        for (int j = 0; j < n - 1 - i; j++)
            if (desc ? a[j] < a[j + 1] : a[j] > a[j + 1])
                swap(a[j], a[j + 1]);
}

void print(int a[], int n) {
    for (int i = 0; i < n; i++) cout << a[i] << " ";
    cout << endl;
}

int main() {
    int a[10] = {5, 2, 9, 1, 7, 3, 8, 6, 4, 0};
    sortArray(a, 10);
    print(a, 10);
    sortArray(a, 10, true);
    print(a, 10);
}
